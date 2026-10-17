from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import aiohttp
from app.indexer.parser import ParsedMedia


@dataclass
class ResolvedMedia:
    tmdb_id: int
    canonical_title: str
    year: Optional[int]
    media_type: str
    matched_alias: Optional[str] = None
    imdb_id: Optional[str] = None
    poster_url: Optional[str] = None
    genres: List[int] = field(default_factory=list)
    overview: Optional[str] = None


class MetadataResolver:
    TMDB_BASE_URL = "https://api.themoviedb.org/3"
    TVDB_BASE_URL = "https://api4.thetvdb.com/v4"

    def __init__(
        self,
        api_key: Optional[str] = None,
        tmdb_api_key: Optional[str] = None,
        tvdb_api_key: Optional[str] = None,
    ):
        self.api_key = tmdb_api_key or api_key or ""
        self.tvdb_api_key = tvdb_api_key
        self._tvdb_token: Optional[str] = None
        self._cache: Dict[str, Optional[ResolvedMedia]] = {}

    async def _fetch_json(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req_params = {"api_key": self.api_key}
        if params:
            req_params.update(params)

        url = f"{self.TMDB_BASE_URL}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=req_params, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {}

    async def _fetch_tvdb_token(self) -> Optional[str]:
        if self._tvdb_token:
            return self._tvdb_token
        if not self.tvdb_api_key:
            return None

        url = f"{self.TVDB_BASE_URL}/login"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={"apikey": self.tvdb_api_key}, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token = (data.get("data") or {}).get("token")
                        self._tvdb_token = token
                        return token
            except Exception:
                pass
        return None

    async def _fetch_tvdb_json(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = await self._fetch_tvdb_token()
        if not token:
            return {}

        url = f"{self.TVDB_BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                pass
        return {}

    async def resolve_tvdb(self, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        """Classify and map TV series via TheTVDB v4 API and link to TMDB ID."""
        data = await self._fetch_tvdb_json("/search", params={"query": parsed.title, "type": "series"})
        results = data.get("data", [])
        if not results:
            return None

        top_candidate = results[0]
        tvdb_id = top_candidate.get("tvdb_id") or top_candidate.get("id")
        if not tvdb_id:
            return None

        # Translate TVDB ID to TMDB series ID via TMDB /find endpoint
        find_data = await self._fetch_json(f"/find/{tvdb_id}", params={"external_source": "tvdb_id"})
        tv_results = find_data.get("tv_results", [])

        if tv_results:
            tmdb_series = tv_results[0]
            canonical = tmdb_series.get("name") or top_candidate.get("name") or parsed.title
            date_str = tmdb_series.get("first_air_date") or top_candidate.get("year") or ""
            year = int(date_str.split("-")[0]) if date_str and "-" in str(date_str) else parsed.year
            poster_path = tmdb_series.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else top_candidate.get("image_url")
            genre_ids = tmdb_series.get("genre_ids", [])
            origin_countries = tmdb_series.get("origin_country", [])

            is_anime = (16 in genre_ids and "JP" in origin_countries) or parsed.media_type == "anime"
            return ResolvedMedia(
                tmdb_id=tmdb_series["id"],
                canonical_title=canonical,
                year=year,
                media_type="anime" if is_anime else "series",
                matched_alias=parsed.title,
                poster_url=poster_url,
                genres=genre_ids,
                overview=tmdb_series.get("overview") or top_candidate.get("overview"),
            )

        # Fallback to direct TVDB series record if TMDB has no mapping
        series_year = int(top_candidate["year"]) if top_candidate.get("year") and str(top_candidate["year"]).isdigit() else parsed.year
        return ResolvedMedia(
            tmdb_id=int(tvdb_id) if str(tvdb_id).isdigit() else 0,
            canonical_title=top_candidate.get("name") or parsed.title,
            year=series_year,
            media_type="anime" if parsed.media_type == "anime" else "series",
            matched_alias=parsed.title,
            poster_url=top_candidate.get("image_url"),
            overview=top_candidate.get("overview"),
        )

    async def resolve(self, parsed: ParsedMedia) -> Optional[ResolvedMedia]:
        cache_key = f"{parsed.title.lower()}:{parsed.year}:{parsed.media_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # If TV cues or series type and TVDB is enabled, try TVDB first
        if self.tvdb_api_key and (parsed.media_type in ("series", "anime") or parsed.season is not None):
            tvdb_res = await self.resolve_tvdb(parsed)
            if tvdb_res:
                self._cache[cache_key] = tvdb_res
                return tvdb_res

        endpoint = "/search/movie" if parsed.media_type != "series" else "/search/tv"
        params: Dict[str, Any] = {"query": parsed.title}
        if parsed.year:
            year_key = "primary_release_year" if parsed.media_type != "series" else "first_air_date_year"
            params[year_key] = parsed.year

        data = await self._fetch_json(endpoint, params)
        results = data.get("results", [])
        if not results:
            # Fallback to TVDB if movie search was empty
            if self.tvdb_api_key:
                tvdb_res = await self.resolve_tvdb(parsed)
                if tvdb_res:
                    self._cache[cache_key] = tvdb_res
                    return tvdb_res
            self._cache[cache_key] = None
            return None

        # Find best candidate
        for item in results:
            item_id = item["id"]
            canonical = item.get("title") or item.get("name") or ""
            date_str = item.get("release_date") or item.get("first_air_date") or ""
            item_year = int(date_str.split("-")[0]) if date_str and "-" in date_str else None

            # Check alternative titles for regional aliases
            alt_data = await self._fetch_json(f"/movie/{item_id}/alternative_titles")
            alt_titles = [t.get("title", "") for t in alt_data.get("titles", [])]

            matched_alias = None
            lower_target = parsed.title.lower()
            if canonical.lower() == lower_target:
                matched_alias = canonical
            else:
                for alias in alt_titles:
                    if alias.lower() == lower_target:
                        matched_alias = alias
                        break

            if matched_alias:
                poster_path = item.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                genre_ids = item.get("genre_ids", [])
                origin_countries = item.get("origin_country", [])

                # Auto-classify as anime if animation genre (16) and origin Japan ('JP'), or parsed as anime
                is_anime = (16 in genre_ids and "JP" in origin_countries) or parsed.media_type == "anime"
                final_media_type = "anime" if is_anime else ("series" if endpoint == "/search/tv" or parsed.media_type == "series" else "movie")

                resolved = ResolvedMedia(
                    tmdb_id=item_id,
                    canonical_title=canonical,
                    year=item_year,
                    media_type=final_media_type,
                    matched_alias=matched_alias,
                    poster_url=poster_url,
                    genres=genre_ids,
                    overview=item.get("overview"),
                )
                self._cache[cache_key] = resolved
                return resolved

        self._cache[cache_key] = None
        return None
