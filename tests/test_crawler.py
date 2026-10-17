import pytest
from unittest.mock import AsyncMock, MagicMock
from app.indexer.crawler import ChannelCrawler
from app.indexer.pipeline import IngestionResult


class MockMessage:
    def __init__(self, id: int, chat_id: int, file_id: str, file_name: str, file_size: int, caption: str = ""):
        self.id = id
        self.chat = MagicMock(id=chat_id)
        self.video = None
        self.document = None
        self.audio = None
        self.caption = caption

        # Simulate media object
        media = MagicMock()
        media.file_id = file_id
        media.file_name = file_name
        media.file_size = file_size
        self.video = media


@pytest.mark.asyncio
async def test_crawler_crawl_channel_success():
    mock_client = MagicMock()
    mock_pipeline = AsyncMock()
    mock_pipeline.process_telegram_message.return_value = IngestionResult(status="matched")

    # Mock get_chat_history generator
    messages = [
        MockMessage(id=101, chat_id=-10012345, file_id="fid_101", file_name="Viduthalai Part 1 1080p.mkv", file_size=2000000000),
        MockMessage(id=102, chat_id=-10012345, file_id="fid_102", file_name="One Piece - 1080.mkv", file_size=800000000),
    ]

    async def async_msg_gen(*args, **kwargs):
        for m in messages:
            yield m

    mock_client.get_chat_history = MagicMock(side_effect=async_msg_gen)

    crawler = ChannelCrawler(client=mock_client, pipeline=mock_pipeline)
    summary = await crawler.crawl_channel(chat_id=-10012345, limit=10)

    assert summary["scanned"] == 2
    assert summary["matched"] == 2
    assert summary["unmatched"] == 0
    assert mock_pipeline.process_telegram_message.call_count == 2


@pytest.mark.asyncio
async def test_crawler_skips_non_media_messages():
    mock_client = MagicMock()
    mock_pipeline = AsyncMock()

    text_msg = MagicMock()
    text_msg.id = 103
    text_msg.video = None
    text_msg.document = None
    text_msg.audio = None

    valid_msg = MockMessage(id=104, chat_id=-10012345, file_id="fid_104", file_name="Baahubali.mkv", file_size=1500000000)

    async def async_msg_gen(*args, **kwargs):
        yield text_msg
        yield valid_msg

    mock_client.get_chat_history = MagicMock(side_effect=async_msg_gen)

    crawler = ChannelCrawler(client=mock_client, pipeline=mock_pipeline)
    summary = await crawler.crawl_channel(chat_id=-10012345)

    assert summary["scanned"] == 2
    assert mock_pipeline.process_telegram_message.call_count == 1


@pytest.mark.asyncio
async def test_reindex_manager_progress_tracking():
    from app.indexer.crawler import ReindexManager

    mock_crawler = AsyncMock()
    mock_crawler.crawl_channel = AsyncMock(return_value={"scanned": 10, "matched": 8, "unmatched": 2})

    reindexer = ReindexManager(crawler=mock_crawler)
    assert reindexer.get_progress()["status"] == "idle"

    started = reindexer.start_reindex(channels=[-1001, -1002])
    assert started is True
    assert reindexer.get_progress()["status"] == "running"

    # Wait for completion
    await reindexer._task
    progress = reindexer.get_progress()
    assert progress["status"] == "completed"
    assert mock_crawler.crawl_channel.call_count == 2

