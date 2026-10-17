import pytest
from unittest.mock import AsyncMock, MagicMock
from app.indexer.parser import ParsedMedia
from app.indexer.resolver import ResolvedMedia
from app.indexer.pipeline import IngestionPipeline, IngestionResult, UnmatchedItem


class InMemoryStorage:
    def __init__(self):
        self.media = []
        self.unmatched = []

    async def save_media(self, media_record: dict) -> None:
        self.media.append(media_record)

    async def save_unmatched(self, item: UnmatchedItem) -> str:
        item_id = f"unmatched_{len(self.unmatched) + 1}"
        item.id = item_id
        self.unmatched.append(item)
        return item_id

    async def get_unmatched(self, item_id: str) -> UnmatchedItem | None:
        for u in self.unmatched:
            if u.id == item_id:
                return u
        return None

    async def remove_unmatched(self, item_id: str) -> None:
        self.unmatched = [u for u in self.unmatched if u.id != item_id]


@pytest.mark.asyncio
async def test_ingest_matched_media():
    storage = InMemoryStorage()
    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(
        return_value=ResolvedMedia(
            tmdb_id=19169,
            canonical_title="Alaipayuthey",
            year=2000,
            media_type="movie",
            matched_alias="Sakhi",
        )
    )

    pipeline = IngestionPipeline(storage=storage, resolver=mock_resolver)

    result = await pipeline.process_telegram_message(
        chat_id=-1001234567,
        message_id=42,
        filename="Sakhi.2000.1080p.mkv",
        caption="Sakhi Telugu movie 1080p",
        file_id="tg_file_sakhi",
        file_size=2048000,
    )

    assert result.status == "matched"
    assert len(storage.media) == 1
    assert storage.media[0]["tmdb_id"] == 19169
    assert storage.media[0]["title"] == "Alaipayuthey"
    assert storage.media[0]["file_id"] == "tg_file_sakhi"
    assert len(storage.unmatched) == 0


@pytest.mark.asyncio
async def test_ingest_unmatched_routes_to_queue_and_1_click_resolves():
    storage = InMemoryStorage()
    mock_resolver = MagicMock()
    # Simulate failed match on TMDB
    mock_resolver.resolve = AsyncMock(return_value=None)

    pipeline = IngestionPipeline(storage=storage, resolver=mock_resolver)

    result = await pipeline.process_telegram_message(
        chat_id=-1001234567,
        message_id=88,
        filename="Unknown_Obscure_Movie_123.mkv",
        caption="Unknown title from 1995",
        file_id="tg_file_unknown",
        file_size=1048576,
    )

    # 1. Verify automatically routed to unmatched queue
    assert result.status == "unmatched"
    assert len(storage.unmatched) == 1
    unmatched_item = storage.unmatched[0]
    assert unmatched_item.chat_id == -1001234567
    assert unmatched_item.message_id == 88
    assert unmatched_item.file_id == "tg_file_unknown"
    assert len(storage.media) == 0

    # 2. 1-Click resolve directly from dashboard without copying Telegram URLs
    resolved_success = await pipeline.resolve_unmatched(
        unmatched_id=unmatched_item.id,
        tmdb_id=5555,
        canonical_title="The Obscure Gem",
        year=1995,
        media_type="movie",
    )

    assert resolved_success is True
    # Promoted to media collection
    assert len(storage.media) == 1
    assert storage.media[0]["tmdb_id"] == 5555
    assert storage.media[0]["title"] == "The Obscure Gem"
    assert storage.media[0]["file_id"] == "tg_file_unknown"
    # Cleaned up from unmatched queue
    assert len(storage.unmatched) == 0
