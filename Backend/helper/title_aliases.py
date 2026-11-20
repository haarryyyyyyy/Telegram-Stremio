"""Alias memory: once an admin fixes a skipped file with an ID, the same file-name title maps to that ID
automatically (next episode, next quality, another upload)."""
import time

import Backend
from Backend.helper.metadata.common import normalize_title
from Backend.logger import LOGGER


def _coll():
    return Backend.db.dbs["tracking"]["title_aliases"]


#----- Movies are keyed with their year (remakes share names); series without one
def _key(title: str, year, media_type: str) -> str:
    year_part = str(year or "") if media_type == "movie" else ""
    return f"{media_type}|{normalize_title(title)}|{year_part}"


async def remember(title: str, year, media_type: str, imdb_id=None, tmdb_id=None) -> None:
    target = imdb_id or (str(tmdb_id) if tmdb_id else None)
    if not title or not target or media_type not in ("movie", "tv"):
        return
    try:
        await _coll().update_one(
            {"_id": _key(title, year, media_type)},
            {"$set": {"id": target, "title": title, "updated_at": time.time()}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.warning(f"[Aliases] Could not remember '{title}': {e}")


#----- The remembered ID ("tt..." or a TMDB number) for this title, or None
async def lookup(title: str, year, media_type: str):
    if not title:
        return None
    try:
        doc = await _coll().find_one({"_id": _key(title, year, media_type)})
    except Exception as e:
        LOGGER.warning(f"[Aliases] Lookup failed for '{title}': {e}")
        return None
    return doc.get("id") if doc else None
