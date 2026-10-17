import re
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ParsedMedia:
    title: str
    year: Optional[int] = None
    media_type: str = "unknown"
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: Optional[str] = None
    codec: Optional[str] = None
    audio: List[str] = field(default_factory=list)
    is_multipart_movie: bool = False


# Common prefix patterns (e.g. @TG_Movies4u_, @channel_name, [ChannelName], t.me/xxx, www.site.com)
_PREFIX_PATTERN = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9]+(?:_[A-Za-z0-9]+)?[_\s\-]+"  # @channel_name_ or @channel_
    r"|\[[^\]]+\][_\s\-]*"                     # [Channel Name]
    r"|\([^\)]+\)[_\s\-]*"                     # (Channel Name)
    r"|https?://\S+[_\s\-]*"                   # Links
    r"|t\.me/\S+[_\s\-]*"                      # t.me links
    r"|www\.\S+[_\s\-]*"                       # www links
    r")",
    re.IGNORECASE,
)

# Delimiter for token boundaries in filenames (handles spaces, dots, underscores, hyphens, brackets)
_SEP = r"(?:^|[\s_.\-\[(])"
_SEP_END = r"(?:$|[\s_.\-\])])"

# Resolution patterns
_QUALITY_PATTERNS = [
    (re.compile(rf"{_SEP}(?:2160p|4k(?:\s*uhd)?){_SEP_END}", re.IGNORECASE), "4K"),
    (re.compile(rf"{_SEP}1080p{_SEP_END}", re.IGNORECASE), "1080p"),
    (re.compile(rf"{_SEP}720p{_SEP_END}", re.IGNORECASE), "720p"),
    (re.compile(rf"{_SEP}480p{_SEP_END}", re.IGNORECASE), "480p"),
]

# Standard SxxExx or SxEE
_SEASON_EPISODE_PATTERN = re.compile(
    rf"{_SEP}S(?P<season>\d{{1,2}})E(?P<episode>\d{{1,4}}){_SEP_END}",
    re.IGNORECASE,
)

# Year pattern (1920 - 2035)
_YEAR_PATTERN = re.compile(rf"{_SEP}(?P<year>(?:19[2-9]\d|20[0-3]\d)){_SEP_END}")

# Tags to strip when cleaning title
_TRASH_TAGS = [
    r"REPACK", r"PROPER", r"UHD", r"SDR", r"HDR(?:10(?:\+)?)?",
    r"DV", r"DOLBY\s*VISION", r"HEVC", r"x26[45]", r"H\.?26[45]",
    r"WEB-?DL", r"WEBRip", r"BluRay", r"BRRip", r"BDRip",
    r"AAC", r"AC3", r"DDP?(?:5\.1)?", r"ATMOS", r"DUAL\s*AUDIO",
    r"MULTI", r"TRUEHD",
]
_TRASH_REGEX = re.compile(rf"{_SEP}(?:" + r"|".join(_TRASH_TAGS) + rf"){_SEP_END}", re.IGNORECASE)


def parse_release(
    filename: str,
    caption: Optional[str] = None,
    channel_username: Optional[str] = None,
) -> ParsedMedia:
    raw_name = filename
    # Remove file extension
    if "." in raw_name:
        raw_name = raw_name.rsplit(".", 1)[0]

    # Check for obfuscated / generic filenames and fall back to caption
    is_obfuscated = not raw_name or raw_name.strip().isdigit() or bool(
        re.match(r"^(?:video|movie|film|file|document|track|tg_doc)[\d_\-]*$", raw_name.strip(), re.IGNORECASE)
    )
    if is_obfuscated and caption:
        for line in caption.splitlines():
            line_str = line.strip()
            if line_str:
                raw_name = line_str
                break

    # 1. Strip explicit channel username if provided
    if channel_username:
        raw_name = re.sub(rf"^@{re.escape(channel_username.lstrip('@'))}[_\s\-]*", "", raw_name, flags=re.IGNORECASE)

    # 2. Strip leading channel handle/link prefix
    cleaned = _PREFIX_PATTERN.sub("", raw_name).strip()

    # 2. Extract quality
    quality = None
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(cleaned):
            quality = label
            break

    # 3. Strip trailing CRC32 checksums like [F2A13840]
    cleaned = re.sub(r"\[[0-9A-Fa-f]{8}\]$", "", cleaned).strip()

    # 4. Extract Season & Episode (Standard SxxExx or Absolute Episode)
    season = None
    episode = None
    media_type = "movie"
    se_match = _SEASON_EPISODE_PATTERN.search(cleaned)
    abs_match = None

    if se_match:
        season = int(se_match.group("season"))
        episode = int(se_match.group("episode"))
        media_type = "series"
    else:
        # Check for absolute episode pattern: e.g. " - 1080", " Ep 1080", " Episode 1080", " E1080"
        abs_p = re.compile(
            r"(?:[\s._\-]+(?:-|ep|episode|e))[\s._\-]+(?P<episode>\d{1,4})(?!p)(?=[\s._\-\[(]|$)",
            re.IGNORECASE,
        )
        abs_match = abs_p.search(cleaned)
        if abs_match:
            episode = int(abs_match.group("episode"))
            media_type = "anime"

    # 5. Extract Year
    year = None
    year_match = _YEAR_PATTERN.search(cleaned)
    if year_match:
        year_val = int(year_match.group("year"))
        # If absolute episode matched the same number as year (e.g. 1080), don't treat it as a year!
        if not (abs_match and abs_match.group("episode") == str(year_val)):
            year = year_val

    # 6. Extract Title
    # Find the earliest boundary among Season/Episode, Absolute Episode, or Year
    cut_pos = len(cleaned)
    if se_match and se_match.start() < cut_pos:
        cut_pos = se_match.start()
    if abs_match and abs_match.start() < cut_pos:
        cut_pos = abs_match.start()
    if year and year_match and year_match.start() < cut_pos and year_match.start() > 0:
        cut_pos = year_match.start()

    raw_title = cleaned[:cut_pos]
    # Check for multi-part movie keywords (Part 1, Chapter 2) before stripping trash tags
    multipart_p = re.compile(rf"{_SEP}(?:Part|Chapter)[\s._\-]*\d+{_SEP_END}", re.IGNORECASE)
    is_multipart = bool(media_type == "movie" and multipart_p.search(raw_title))

    # Remove trash tags from title
    raw_title = _TRASH_REGEX.sub(" ", raw_title)
    # Replace underscores, dots, hyphens with spaces
    title = re.sub(r"[_.\-]+", " ", raw_title).strip()
    title = re.sub(r"\s+", " ", title)

    return ParsedMedia(
        title=title,
        year=year,
        media_type=media_type,
        season=season,
        episode=episode,
        quality=quality,
        is_multipart_movie=is_multipart,
    )
