import asyncio
import logging
from typing import Optional, List, Dict, Any, Callable
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from app.indexer.pipeline import IngestionPipeline, IngestionResult

logger = logging.getLogger(__name__)


def extract_media(message: Message):
    """Extract media object from message (video, document, audio)."""
    return (
        getattr(message, "video", None)
        or getattr(message, "document", None)
        or getattr(message, "audio", None)
    )


class ChannelCrawler:
    def __init__(self, client: Client, pipeline: IngestionPipeline):
        self.client = client
        self.pipeline = pipeline

    async def crawl_channel(
        self,
        chat_id: int | str,
        limit: Optional[int] = None,
        delay: float = 0.05,
        on_progress: Optional[Callable[[Dict[str, int]], None]] = None,
    ) -> Dict[str, int]:
        """
        Scans a Telegram channel backwards/forwards, extracting and indexing all media items.
        Handles flood waits and tracks progress.
        """
        scanned = 0
        matched = 0
        unmatched = 0

        try:
            async for msg in self.client.get_chat_history(chat_id=chat_id, limit=limit):
                scanned += 1
                media = extract_media(msg)
                if not media:
                    continue

                file_id = getattr(media, "file_id", "")
                file_name = getattr(media, "file_name", "") or getattr(media, "name", "")
                file_size = getattr(media, "file_size", 0)
                caption = getattr(msg, "caption", "") or ""

                try:
                    result: IngestionResult = await self.pipeline.process_telegram_message(
                        chat_id=msg.chat.id,
                        message_id=msg.id,
                        filename=file_name,
                        caption=caption,
                        file_id=file_id,
                        file_size=file_size,
                    )
                    if result and result.status == "matched":
                        matched += 1
                    else:
                        unmatched += 1
                except Exception as e:
                    logger.error(f"Error ingesting message {msg.id} in chat {chat_id}: {e}")
                    unmatched += 1

                if on_progress and scanned % 10 == 0:
                    on_progress({"scanned": scanned, "matched": matched, "unmatched": unmatched})

                if delay > 0:
                    await asyncio.sleep(delay)

        except FloodWait as e:
            logger.warning(f"Hit FloodWait of {e.value}s while crawling {chat_id}")
            await asyncio.sleep(e.value or 1)
        except Exception as e:
            logger.error(f"Error during crawl of chat {chat_id}: {e}")
            raise

        final_summary = {"scanned": scanned, "matched": matched, "unmatched": unmatched}
        if on_progress:
            on_progress(final_summary)
        return final_summary

    def setup_listener(self, chat_ids: Optional[List[int | str]] = None):
        """Register live real-time incoming message handler for active channels."""
        chat_filter = filters.chat(chat_ids) if chat_ids else filters.all

        @self.client.on_message(chat_filter & (filters.video | filters.document | filters.audio))
        async def _on_new_media(client: Client, message: Message):
            media = extract_media(message)
            if not media:
                return

            file_id = getattr(media, "file_id", "")
            file_name = getattr(media, "file_name", "") or getattr(media, "name", "")
            file_size = getattr(media, "file_size", 0)
            caption = getattr(message, "caption", "") or ""

            try:
                await self.pipeline.process_telegram_message(
                    chat_id=message.chat.id,
                    message_id=message.id,
                    filename=file_name,
                    caption=caption,
                    file_id=file_id,
                    file_size=file_size,
                )
                logger.info(f"Live indexed new media from chat {message.chat.id}: {file_name}")
            except Exception as e:
                logger.error(f"Failed to live-index message {message.id}: {e}")


class ReindexManager:
    """Manages full re-indexing lifecycle across multiple channels with live UI status."""
    def __init__(self, crawler: ChannelCrawler):
        self.crawler = crawler
        self.status: str = "idle"  # idle | running | completed | error
        self.scanned: int = 0
        self.matched: int = 0
        self.unmatched: int = 0
        self.current_channel: str = ""
        self.error_message: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    def get_progress(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "scanned": self.scanned,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "current_channel": self.current_channel,
            "error_message": self.error_message,
        }

    async def _run(self, channels: List[int | str], limit: Optional[int] = None):
        self.status = "running"
        self.scanned = 0
        self.matched = 0
        self.unmatched = 0
        self.error_message = None

        def _update_cb(metrics: Dict[str, int]):
            self.scanned = metrics.get("scanned", 0)
            self.matched = metrics.get("matched", 0)
            self.unmatched = metrics.get("unmatched", 0)

        try:
            for ch in channels:
                self.current_channel = str(ch)
                await self.crawler.crawl_channel(chat_id=ch, limit=limit, on_progress=_update_cb)
            self.status = "completed"
        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            logger.error(f"Re-index failed: {e}")

    def start_reindex(self, channels: List[int | str], limit: Optional[int] = None) -> bool:
        if self.status == "running":
            return False
        self.status = "running"
        self.scanned = 0
        self.matched = 0
        self.unmatched = 0
        self.error_message = None
        self._task = asyncio.create_task(self._run(channels=channels, limit=limit))
        return True
