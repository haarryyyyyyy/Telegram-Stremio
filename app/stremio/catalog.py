import time
import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Any


@dataclass
class LibraryMediaItem:
    tmdb_id: int
    title: str
    year: Optional[int]
    media_type: str  # "movie" | "series" | "anime"
    poster_url: Optional[str]
    file_id: str
    quality: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None


@dataclass
class StremioMetaItem:
    id: str  # e.g. "tmdb:101"
    type: str  # "movie" | "series"
    name: str
    poster: Optional[str]
    year: Optional[int] = None
    genres: List[str] = field(default_factory=list)


class CatalogManager:
    ROTATION_INTERVAL_SECONDS = 900  # 15 minutes

    def __init__(
        self,
        library_provider: Optional[Callable] = None,
        recommendation_provider: Optional[Callable] = None,
        db: Optional[Any] = None,
        spotlight_interval_seconds: int = 900,
    ):
        if db:
            self.library_provider = library_provider or db.get_library_items
            self.recommendation_provider = recommendation_provider or db.get_recently_watched_ids
        else:
            self.library_provider = library_provider or (lambda: [])
            self.recommendation_provider = recommendation_provider
        self.ROTATION_INTERVAL_SECONDS = spotlight_interval_seconds

    async def get_catalog(
        self,
        token: str,
        catalog_type: str,
        catalog_id: str,
        skip: int = 0,
        current_timestamp: Optional[float] = None,
    ) -> List[StremioMetaItem]:
        all_items = self.library_provider()

        # Filter by media type and deduplicate by tmdb_id
        unique_by_id: Dict[int, LibraryMediaItem] = {}
        for item in all_items:
            # Map "anime" to "series" or "movie" for Stremio protocol if needed
            item_type = item.media_type
            target_type = catalog_type
            if item_type == target_type or (catalog_type == "series" and item_type == "anime"):
                if item.tmdb_id not in unique_by_id:
                    unique_by_id[item.tmdb_id] = item

        deduped_items = list(unique_by_id.values())
        if not deduped_items:
            return []

        now = current_timestamp if current_timestamp is not None else time.time()

        if catalog_id == "spotlight":
            # 15-minute rotation window
            time_slot = int(now // self.ROTATION_INTERVAL_SECONDS)
            # Deterministic seeded shuffle based on the 15-minute slot
            rng = random.Random(time_slot)
            shuffled = list(deduped_items)
            rng.shuffle(shuffled)
            deduped_items = shuffled
        elif catalog_id == "recommended" and self.recommendation_provider:
            # Filter and order based on user's personal recommendation IDs
            rec_ids = self.recommendation_provider(token)
            deduped_items = [unique_by_id[tmdb_id] for tmdb_id in rec_ids if tmdb_id in unique_by_id]

        result = []
        for item in deduped_items[skip:]:
            result.append(
                StremioMetaItem(
                    id=f"tmdb:{item.tmdb_id}",
                    type="series" if item.media_type in ("series", "anime") else "movie",
                    name=item.title,
                    poster=item.poster_url,
                    year=item.year,
                )
            )

        return result

    async def search_catalog(self, catalog_type: str, query: str) -> List[StremioMetaItem]:
        """Search the media catalog by title (case-insensitive) for Nuvio/Stremio search queries."""
        items = self.library_provider()
        if hasattr(items, "__await__"):
            items = await items

        q_lower = query.strip().lower()
        unique_by_id: Dict[int, LibraryMediaItem] = {}

        for item in items:
            item_type = item.media_type
            if item_type == catalog_type or (catalog_type == "series" and item_type == "anime") or (catalog_type == "movie" and item_type == "movie"):
                if q_lower in item.title.lower():
                    if item.tmdb_id not in unique_by_id:
                        unique_by_id[item.tmdb_id] = item

        result = []
        for item in unique_by_id.values():
            result.append(
                StremioMetaItem(
                    id=f"tmdb:{item.tmdb_id}",
                    type="series" if item.media_type in ("series", "anime") else "movie",
                    name=item.title,
                    poster=item.poster_url,
                    year=item.year,
                )
            )
        return result

