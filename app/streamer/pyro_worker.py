import asyncio
import logging
from typing import List, Optional, Dict
from pyrogram import Client, raw
from pyrogram.file_id import FileId
from pyrogram.session import Auth, Session
from pyrogram.errors import AuthBytesInvalid, FloodWait, RPCError

from app.streamer.multiplexer import BotWorker

logger = logging.getLogger(__name__)


def _is_session_ready(session) -> bool:
    if not session:
        return False
    is_started = getattr(session, "is_started", None)
    if is_started is None:
        return True
    if hasattr(is_started, "is_set") and callable(is_started.is_set):
        res = is_started.is_set()
        # In case is_started.is_set is an AsyncMock or mock object
        if hasattr(res, "__bool__"):
            return bool(res)
        return True
    return True


class PyroforkBotWorker(BotWorker):
    def __init__(self, client: Client, bot_id: int):
        self.client = client
        self.bot_id = bot_id
        self._session_lock = asyncio.Lock()

    async def _get_media_session(self, dc_id: int) -> Session:
        """Retrieve existing media session or establish and authenticate a new one for the target DC."""
        media_session = self.client.media_sessions.get(dc_id)
        if _is_session_ready(media_session):
            return media_session

        async with self._session_lock:
            # Double-check inside lock
            media_session = self.client.media_sessions.get(dc_id)
            if _is_session_ready(media_session):
                return media_session

            test_mode = await self.client.storage.test_mode()
            current_dc = await self.client.storage.dc_id()

            if dc_id != current_dc:
                auth_key = await Auth(self.client, dc_id, test_mode).create()
            else:
                auth_key = await self.client.storage.auth_key()

            session = Session(self.client, dc_id, auth_key, test_mode, is_media=True)
            session.no_updates = True
            session.timeout = 30
            session.sleep_threshold = 60

            await session.start()

            if dc_id != current_dc:
                for _ in range(6):
                    try:
                        exported = await self.client.invoke(raw.functions.auth.ExportAuthorization(dc_id=dc_id))
                        await session.send(raw.functions.auth.ImportAuthorization(id=exported.id, bytes=exported.bytes))
                        break
                    except AuthBytesInvalid:
                        await asyncio.sleep(0.5)
                    except FloodWait as e:
                        await asyncio.sleep(e.value or 1)
                    except (RPCError, OSError, asyncio.TimeoutError, TimeoutError):
                        await asyncio.sleep(1)
                else:
                    await session.stop()
                    raise RuntimeError(f"Failed to export/import auth to DC {dc_id} on Bot {self.bot_id}")

            self.client.media_sessions[dc_id] = session
            return session

    async def prewarm_dcs(self, target_dcs: Optional[List[int]] = None):
        """Pre-warm media sessions on startup to eliminate initial GetFile auth lag."""
        if target_dcs is None:
            target_dcs = [1, 2, 4, 5]

        for dc in target_dcs:
            try:
                await self._get_media_session(dc)
                logger.info(f"Bot {self.bot_id}: Pre-warmed media session for DC {dc}")
            except Exception as e:
                logger.warning(f"Bot {self.bot_id}: Could not pre-warm DC {dc}: {e}")

    async def fetch_chunk(self, file_id: str, offset: int, limit: int) -> bytes:
        """Fetch a single byte chunk from Telegram MTProto."""
        try:
            file_id_obj = FileId.decode(file_id)
        except Exception as e:
            raise ValueError(f"Invalid Telegram file_id: {e}")

        location = raw.types.InputDocumentFileLocation(
            id=file_id_obj.media_id,
            access_hash=file_id_obj.access_hash,
            file_reference=file_id_obj.file_reference,
            thumb_size=file_id_obj.thumbnail_size,
        )

        session = await self._get_media_session(file_id_obj.dc_id)

        try:
            res = await session.send(
                raw.functions.upload.GetFile(
                    location=location,
                    offset=offset,
                    limit=limit,
                )
            )
            return getattr(res, "bytes", b"")
        except FloodWait as e:
            logger.warning(f"Bot {self.bot_id} hit FloodWait of {e.value}s")
            raise
        except Exception as e:
            logger.error(f"Bot {self.bot_id} fetch error at offset {offset}: {e}")
            raise


class BotPoolManager:
    def __init__(self, api_id: int, api_hash: str, bot_tokens: List[str]):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_tokens = [tok.strip() for tok in bot_tokens if tok.strip()]
        self.bot_clients: Dict[str, Client] = {}
        self.bot_workers: Dict[str, PyroforkBotWorker] = {}

    @property
    def clients(self) -> List[Client]:
        return list(self.bot_clients.values())

    @property
    def workers(self) -> List[PyroforkBotWorker]:
        return list(self.bot_workers.values())

    async def add_bot(self, token: str, prewarm: bool = True) -> Optional[PyroforkBotWorker]:
        """Dynamically start and register a new bot client at runtime."""
        token = token.strip()
        if not token:
            return None
        if token in self.bot_clients:
            return self.bot_workers.get(token)

        bot_idx = len(self.bot_clients)
        client = Client(
            name=f"stream_bot_{token[:8]}_{bot_idx}",
            api_id=self.api_id,
            api_hash=self.api_hash,
            bot_token=token,
            in_memory=True,
            no_updates=True,
            workers=6,
            max_concurrent_transmissions=10,
        )
        try:
            await client.start()
            worker = PyroforkBotWorker(client=client, bot_id=bot_idx)
            self.bot_clients[token] = client
            self.bot_workers[token] = worker

            if prewarm:
                await worker.prewarm_dcs()
            logger.info(f"Dynamically started bot client {bot_idx} ({token[:8]}...)")
            return worker
        except Exception as e:
            logger.error(f"Failed to dynamically start bot {token[:8]}: {e}")
            raise

    async def remove_bot(self, token: str) -> bool:
        """Dynamically stop and deregister a bot client at runtime."""
        token = token.strip()
        client = self.bot_clients.pop(token, None)
        self.bot_workers.pop(token, None)

        if client:
            try:
                await client.stop()
                logger.info(f"Dynamically stopped bot ({token[:8]}...)")
                return True
            except Exception as e:
                logger.warning(f"Error stopping bot client: {e}")
                return True
        return False

    async def start_all(self, prewarm: bool = True):
        """Start all configured bot clients and pre-warm DC connections."""
        for token in self.bot_tokens:
            try:
                await self.add_bot(token, prewarm=prewarm)
            except Exception as e:
                logger.warning(f"Skipping initial bot ({token[:8]}...): {e}")

    def get_workers(self) -> List[BotWorker]:
        return list(self.bot_workers.values())

    def get_tokens(self) -> List[str]:
        return list(self.bot_clients.keys())

    async def stop_all(self):
        """Gracefully stop all client connections."""
        for client in list(self.bot_clients.values()):
            try:
                await client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client: {e}")
        self.bot_clients.clear()
        self.bot_workers.clear()

