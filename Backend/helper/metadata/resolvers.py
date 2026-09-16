"""Priority chains for metadata resolution.

Anime  : Kitsu > TVDB > TMDB > Cinemeta
Movies : TMDB > Cinemeta
Series : TVDB > Cinemeta > TMDB
"""
from __future__ import annotations

import re
from typing import Optional

from Backend.helper.metadata.common import split_default_id, title_similarity, CINEMETA_THRESHOLD
from Backend.helper.metadata.providers import cinemeta, kitsu, tmdb, tvdb
from Backend.logger import LOGGER


def title_search_candidates(title: str) -> list[str]:
    """Generate clean candidate titles for metadata searching by stripping channel prefixes,
    uploader tags, website domains, and media noise.
    """
    if not title:
        return []

    raw = title.strip()
    candidates = [raw]

    # Iteratively strip leading tags (brackets, @channel, t.me, domains, separators)
    cleaned = raw
    prev = None
    while cleaned != prev and len(cleaned) >= 2:
        prev = cleaned
        # Bracketed prefix
        cleaned = re.sub(r"^[\[({【][^\])}】]+[\])}】]\s*", "", cleaned).strip()
        # @channel or t.me
        cleaned = re.sub(r"^(?:join\s*|join\s*:?\s*)?(?:@|t\.me[/_]|telegram\.me[/_]|telegram\.dog[/_])[\w_.]+\s*[-:|~•]?\s*", "", cleaned, flags=re.IGNORECASE).strip()
        # domain
        cleaned = re.sub(r"^(?:www\.)?[A-Za-z0-9_-]+\.(?:com|net|org|in|vip|me|to|is|cc|mov|tv|site|xyz|online|club|top|tech|info|co|biz|live|pro|click|download|baby|bar|wtf|fun|space|monster|pw|icu|best|buzz|uno|art|run)\s*[-:|~•]?\s*", "", cleaned, flags=re.IGNORECASE).strip()
        # leading separator
        cleaned = re.sub(r"^[^\s\-:|~•]+\s*[-:|~•]\s*", "", cleaned).strip()
        if cleaned and cleaned not in candidates and len(cleaned) >= 2:
            candidates.append(cleaned)

    # Also strip all bracketed tags anywhere in the string
    un_all = re.sub(r"[\[({【][^\])}】]*[\])}】]", " ", raw).strip()
    un_all = re.sub(r"\s+", " ", un_all).strip()
    if un_all and un_all not in candidates and len(un_all) >= 2:
        candidates.append(un_all)

    # Add dot/underscore to space variants
    for c in list(candidates):
        dot_spaced = re.sub(r"[._]+", " ", c).strip()
        if dot_spaced and dot_spaced not in candidates:
            candidates.append(dot_spaced)

    # Strip trailing noise tokens (audio, quality, codec, language)
    noise_pattern = re.compile(
        r"(?i)\b(?:dual\s*audio|multi\s*audio|multi\s*sub|esub|hindi|tamil|telugu|malayalam|kannada|english|"
        r"korean|japanese|chinese|spanish|french|german|italian|bengali|marathi|punjabi|"
        r"1080p|720p|480p|2160p|4k|uhd|hdrip|web-?dl|webrip|bluray|bdrip|brrip|hdtv|dvdrip|"
        r"hevc|x264|x265|h264|h265|avc|aac|ddp?5\.1|dd5\.1|dts|truehd|atmos|10bit|8bit|hq)\b.*$",
        re.IGNORECASE,
    )
    for c in list(candidates):
        stripped = noise_pattern.sub("", c).strip()
        stripped = re.sub(r"[\s._\-:|~•]+$", "", stripped).strip()
        if stripped and len(stripped) >= 2 and stripped not in candidates:
            candidates.append(stripped)

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        norm = c.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            unique_candidates.append(c)

    return unique_candidates


# ── Movies: TMDB > Cinemeta ──────────────────────────────────────────────────

async def resolve_movie(
    title: str,
    encoded_string,
    year=None,
    quality=None,
    default_id=None,
) -> Optional[dict]:
    imdb_id, tmdb_id, explicit_imdb, force_tmdb = split_default_id(default_id)

    # Explicit TMDB id
    if tmdb_id and force_tmdb:
        movie = await tmdb.details("movie", tmdb_id)
        if movie:
            return tmdb.build_movie_payload(movie, quality, encoded_string)

    # Explicit IMDb id → Cinemeta
    if imdb_id and explicit_imdb:
        try:
            detail = await cinemeta.cached_detail(imdb_id, "movie")
            if detail:
                return cinemeta.build_movie_payload(detail, imdb_id, title, quality, encoded_string)
        except Exception as e:
            LOGGER.warning(f"Cinemeta explicit movie fetch failed [{imdb_id}]: {e}")

    candidates = title_search_candidates(title)

    # 1) TMDB first
    matched_title = title
    if not tmdb_id:
        for cand in candidates:
            hit = await tmdb.safe_search(cand, "movie", year)
            if hit == "AMBIGUOUS":
                LOGGER.warning(
                    f"[MOVIE] Ambiguous TMDb movie match detected for '{cand}' (year={year}) -> forwarding to skip channel."
                )
                return None
            if hit:
                tmdb_id = hit.id
                matched_title = cand
                break

    if tmdb_id:
        movie = await tmdb.details("movie", tmdb_id)
        if movie:
            LOGGER.info(f"[MOVIE] TMDB hit for '{matched_title}' (original='{title}', year={year})")
            return tmdb.build_movie_payload(movie, quality, encoded_string)

    # 2) Cinemeta / IMDb fallback search
    LOGGER.info(f"[MOVIE] TMDB miss for '{title}' (year={year}) -> Cinemeta / IMDb search")
    if not imdb_id:
        for cand in candidates:
            res_id = await cinemeta.safe_search(cand, "movie", year)
            if res_id == "AMBIGUOUS":
                LOGGER.warning(
                    f"[MOVIE] Ambiguous Cinemeta/IMDb movie match detected for '{cand}' (year={year}) -> forwarding to skip channel."
                )
                return None
            if res_id:
                imdb_id = res_id
                matched_title = cand
                break

    if imdb_id:
        try:
            detail = await cinemeta.cached_detail(imdb_id, "movie")
            if detail:
                for cand in candidates:
                    sim = title_similarity(cand, detail.get("title", ""))
                    if sim >= CINEMETA_THRESHOLD or explicit_imdb:
                        LOGGER.info(f"[MOVIE] Cinemeta/IMDb hit for '{cand}' -> '{detail.get('title')}' [{imdb_id}]")
                        return cinemeta.build_movie_payload(detail, imdb_id, cand, quality, encoded_string)
                LOGGER.info(
                    f"[MOVIE] Cinemeta title mismatch for '{title}': "
                    f"got '{detail.get('title')}'"
                )
        except Exception as e:
            LOGGER.warning(f"Cinemeta movie fetch failed [{title}]: {e}")

    LOGGER.info(f"[MOVIE] No metadata found for '{title}' (year={year})")
    return None


# ── Series: TVDB > Cinemeta > TMDB ────────────────────────────────────────────

async def resolve_series(
    title: str,
    season: int,
    episode: int,
    encoded_string,
    year=None,
    quality=None,
    default_id=None,
) -> Optional[dict]:
    imdb_id, tmdb_id, explicit_imdb, force_tmdb = split_default_id(default_id)

    # Explicit overrides skip the chain
    if tmdb_id and force_tmdb:
        tv = await tmdb.details("tv", tmdb_id)
        if tv:
            ep = await tmdb.episode_details(tmdb_id, season, episode)
            return tmdb.build_tv_payload(tv, ep, season, episode, quality, encoded_string)

    if imdb_id and explicit_imdb:
        try:
            detail = await cinemeta.cached_detail(imdb_id, "tvSeries")
            ep = await cinemeta.cached_season(imdb_id, season, episode)
            if detail:
                return cinemeta.build_tv_payload(
                    detail, ep or {}, imdb_id, title, season, episode, quality, encoded_string
                )
        except Exception as e:
            LOGGER.warning(f"Cinemeta explicit TV fetch failed [{imdb_id}]: {e}")

    candidates = title_search_candidates(title)

    # 1) TVDB
    for cand in candidates:
        try:
            result = await tvdb.fetch_series_metadata(
                cand, season, episode, encoded_string, year=year, quality=quality
            )
            if result:
                LOGGER.info(f"[SERIES] TVDB hit for '{cand}' S{season:02d}E{episode:02d}")
                return result
        except Exception as e:
            LOGGER.warning(f"[SERIES] TVDB error for '{cand}': {e}")

    # 2) Cinemeta
    LOGGER.info(f"[SERIES] TVDB miss for '{title}' -> Cinemeta")
    if not imdb_id:
        for cand in candidates:
            imdb_id = await cinemeta.safe_search(cand, "tvSeries", year)
            if imdb_id:
                break
    if imdb_id:
        try:
            detail = await cinemeta.cached_detail(imdb_id, "tvSeries")
            ep = await cinemeta.cached_season(imdb_id, season, episode)
            if detail:
                for cand in candidates:
                    sim = title_similarity(cand, detail.get("title", ""))
                    if sim >= CINEMETA_THRESHOLD or explicit_imdb:
                        return cinemeta.build_tv_payload(
                            detail, ep or {}, imdb_id, cand, season, episode, quality, encoded_string
                        )
                LOGGER.info(
                    f"[SERIES] Cinemeta title mismatch for '{title}': "
                    f"got '{detail.get('title')}'"
                )
        except Exception as e:
            LOGGER.warning(f"Cinemeta TV fetch failed [{title}]: {e}")

    # 3) TMDB
    LOGGER.info(f"[SERIES] Cinemeta miss for '{title}' -> TMDB")
    if not tmdb_id:
        for cand in candidates:
            hit = await tmdb.safe_search(cand, "tv", year)
            if hit:
                tmdb_id = hit.id
                break
    if tmdb_id:
        tv = await tmdb.details("tv", tmdb_id)
        if tv:
            ep = await tmdb.episode_details(tmdb_id, season, episode)
            return tmdb.build_tv_payload(tv, ep, season, episode, quality, encoded_string)

    LOGGER.info(f"[SERIES] No metadata for '{title}' S{season:02d}E{episode:02d}")
    return None


# ── Anime: Kitsu > TVDB > TMDB > Cinemeta ─────────────────────────────────────

async def resolve_anime_tv(
    title: str,
    season,
    episode: int,
    encoded_string,
    year=None,
    quality=None,
    absolute: bool = False,
) -> Optional[dict]:
    """Resolve anime episode metadata.

    absolute=True (or season is None): orphan/absolute numbering
    e.g. "One Piece 1223 720.mkv" → Kitsu absolute episode 1223.
    """
    absolute = bool(absolute or season is None)
    label = f"E{episode}" if absolute else f"S{int(season):02d}E{int(episode):02d}"

    candidates = title_search_candidates(title)

    # 1) Kitsu (native absolute-episode support via ani.zip)
    for cand in candidates:
        try:
            result = await kitsu.fetch_anime_tv(
                cand, season, episode, encoded_string,
                year=year, quality=quality, absolute=absolute,
            )
            if result:
                LOGGER.info(f"[ANIME] Kitsu hit for '{cand}' {label}")
                return result
        except Exception as e:
            LOGGER.warning(f"[ANIME] Kitsu error for '{cand}': {e}")

    # For absolute episodes without a mapped season, use season 1 + absolute number
    # so downstream providers and Stremio still get a valid S/E pair.
    use_season = 1 if absolute else int(season)
    use_episode = int(episode)

    # 2) TVDB
    for cand in candidates:
        try:
            result = await tvdb.fetch_series_metadata(
                cand, use_season, use_episode, encoded_string, year=year, quality=quality
            )
            if result:
                if absolute:
                    result["season_number"] = result.get("season_number") or use_season
                    result["episode_number"] = use_episode
                    result["absolute_episode"] = use_episode
                LOGGER.info(f"[ANIME] TVDB hit for '{cand}' {label}")
                return result
        except Exception as e:
            LOGGER.warning(f"[ANIME] TVDB error for '{cand}': {e}")

    # 3) TMDB
    for cand in candidates:
        hit = await tmdb.safe_search(cand, "tv", year)
        if hit:
            tv = await tmdb.details("tv", hit.id)
            if tv:
                ep = None if absolute else await tmdb.episode_details(hit.id, use_season, use_episode)
                LOGGER.info(f"[ANIME] TMDB hit for '{cand}' {label}")
                payload = tmdb.build_tv_payload(tv, ep, use_season, use_episode, quality, encoded_string)
                if absolute:
                    payload["absolute_episode"] = use_episode
                    if not payload.get("episode_title") or payload["episode_title"].startswith("S"):
                        payload["episode_title"] = f"Episode {use_episode}"
                return payload

    # 4) Cinemeta (least priority)
    for cand in candidates:
        imdb_id = await cinemeta.safe_search(cand, "tvSeries", year)
        if imdb_id:
            try:
                detail = await cinemeta.cached_detail(imdb_id, "tvSeries")
                ep = {} if absolute else await cinemeta.cached_season(imdb_id, use_season, use_episode)
                if detail:
                    LOGGER.info(f"[ANIME] Cinemeta hit for '{cand}' {label}")
                    payload = cinemeta.build_tv_payload(
                        detail, ep or {}, imdb_id, cand, use_season, use_episode, quality, encoded_string
                    )
                    if absolute:
                        payload["absolute_episode"] = use_episode
                        if not (ep or {}).get("title"):
                            payload["episode_title"] = f"Episode {use_episode}"
                    return payload
            except Exception as e:
                LOGGER.warning(f"[ANIME] Cinemeta error for '{cand}': {e}")

    LOGGER.info(f"[ANIME] No metadata for '{title}' {label}")
    return None


async def resolve_anime_movie(
    title: str,
    encoded_string,
    year=None,
    quality=None,
) -> Optional[dict]:
    candidates = title_search_candidates(title)

    # 1) Kitsu
    for cand in candidates:
        try:
            result = await kitsu.fetch_anime_movie(cand, encoded_string, year=year, quality=quality)
            if result:
                LOGGER.info(f"[ANIME] Kitsu movie hit for '{cand}'")
                return result
        except Exception as e:
            LOGGER.warning(f"[ANIME] Kitsu movie error for '{cand}': {e}")

    # 2) TVDB
    for cand in candidates:
        try:
            result = await tvdb.fetch_movie_metadata(cand, encoded_string, year=year, quality=quality)
            if result:
                LOGGER.info(f"[ANIME] TVDB movie hit for '{cand}'")
                return result
        except Exception as e:
            LOGGER.warning(f"[ANIME] TVDB movie error for '{cand}': {e}")

    # 3) TMDB
    for cand in candidates:
        hit = await tmdb.safe_search(cand, "movie", year)
        if hit:
            movie = await tmdb.details("movie", hit.id)
            if movie:
                LOGGER.info(f"[ANIME] TMDB movie hit for '{cand}'")
                return tmdb.build_movie_payload(movie, quality, encoded_string)

    # 4) Cinemeta
    for cand in candidates:
        imdb_id = await cinemeta.safe_search(cand, "movie", year)
        if imdb_id:
            try:
                detail = await cinemeta.cached_detail(imdb_id, "movie")
                if detail:
                    LOGGER.info(f"[ANIME] Cinemeta movie hit for '{cand}'")
                    return cinemeta.build_movie_payload(detail, imdb_id, cand, quality, encoded_string)
            except Exception as e:
                LOGGER.warning(f"[ANIME] Cinemeta movie error for '{cand}': {e}")

    LOGGER.info(f"[ANIME] No movie metadata for '{title}'")
    return None
