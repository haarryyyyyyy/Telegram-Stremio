from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from app.indexer.parser import parse_release, ParsedMedia
from app.indexer.resolver import MetadataResolver, ResolvedMedia


@dataclass
class UnmatchedItem:
    chat_id: int
    message_id: int
    filename: str
    file_id: str
    file_size: int
    caption: Optional[str] = None
    parsed_title: str = ""
    parsed_year: Optional[int] = None
    quality: Optional[str] = None
    id: Optional[str] = None


@dataclass
class IngestionResult:
    status: str  # "matched" | "unmatched" | "skipped"
    media_record: Optional[Dict[str, Any]] = None
    unmatched_id: Optional[str] = None


class IngestionPipeline:
    def __init__(self, storage: Any, resolver: MetadataResolver):
        self.storage = storage
        self.resolver = resolver

    async def process_telegram_message(
        self,
        chat_id: int,
        message_id: int,
        filename: str,
        caption: Optional[str] = None,
        file_id: str = "",
        file_size: int = 0,
        channel_username: Optional[str] = None,
    ) -> IngestionResult:
        # 1. Parse raw filename & caption
        parsed: ParsedMedia = parse_release(
            filename=filename,
            caption=caption,
            channel_username=channel_username,
        )

        # 2. Query TMDB/Cinemeta resolver with regional alias support
        resolved: Optional[ResolvedMedia] = await self.resolver.resolve(parsed)

        if resolved:
            # Automatic match found
            media_record = {
                "tmdb_id": resolved.tmdb_id,
                "title": resolved.canonical_title,
                "matched_alias": resolved.matched_alias,
                "year": resolved.year,
                "media_type": resolved.media_type,
                "poster_url": resolved.poster_url,
                "file_id": file_id,
                "file_size": file_size,
                "chat_id": chat_id,
                "message_id": message_id,
                "quality": parsed.quality,
                "season": parsed.season,
                "episode": parsed.episode,
            }
            await self.storage.save_media(media_record)
            return IngestionResult(status="matched", media_record=media_record)

        # 3. No match found -> Route to 1-Click Unmatched Queue
        unmatched = UnmatchedItem(
            chat_id=chat_id,
            message_id=message_id,
            filename=filename,
            caption=caption,
            file_id=file_id,
            file_size=file_size,
            parsed_title=parsed.title,
            parsed_year=parsed.year,
            quality=parsed.quality,
        )
        unmatched_id = await self.storage.save_unmatched(unmatched)
        return IngestionResult(status="unmatched", unmatched_id=unmatched_id)

    async def resolve_unmatched(
        self,
        unmatched_id: str,
        tmdb_id: int,
        canonical_title: str,
        year: Optional[int],
        media_type: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> bool:
        """Promote an item from unmatched queue into media catalog with 1-click."""
        unmatched: Optional[UnmatchedItem] = await self.storage.get_unmatched(unmatched_id)
        if not unmatched:
            return False

        media_record = {
            "tmdb_id": tmdb_id,
            "title": canonical_title,
            "year": year,
            "media_type": media_type,
            "file_id": unmatched.file_id,
            "file_size": unmatched.file_size,
            "chat_id": unmatched.chat_id,
            "message_id": unmatched.message_id,
            "quality": unmatched.quality,
            "season": season,
            "episode": episode,
        }
        await self.storage.save_media(media_record)
        await self.storage.remove_unmatched(unmatched_id)
        return True
