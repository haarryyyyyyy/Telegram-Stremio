import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pyrogram.file_id import FileId, FileType
from app.streamer.pyro_worker import PyroforkBotWorker, BotPoolManager


@pytest.fixture
def mock_file_id():
    fid = FileId(
        file_type=FileType.DOCUMENT,
        dc_id=4,
        media_id=987654321,
        access_hash=123456789,
        file_reference=b"test_ref",
    )
    return fid.encode()


@pytest.mark.asyncio
async def test_pyro_worker_fetch_chunk(mock_file_id):
    mock_client = MagicMock()
    mock_client.media_sessions = {}
    mock_session = AsyncMock()
    mock_session.is_started = MagicMock()
    mock_session.is_started.is_set.return_value = True
    mock_response = MagicMock()
    mock_response.bytes = b"EXACT_TELEGRAM_CHUNK_BYTES"
    mock_session.send.return_value = mock_response

    mock_client.media_sessions[4] = mock_session

    worker = PyroforkBotWorker(client=mock_client, bot_id=1)
    chunk = await worker.fetch_chunk(file_id=mock_file_id, offset=0, limit=1048576)

    assert chunk == b"EXACT_TELEGRAM_CHUNK_BYTES"
    mock_session.send.assert_awaited_once()
    sent_request = mock_session.send.call_args[0][0]
    assert sent_request.offset == 0
    assert sent_request.limit == 1048576
    assert sent_request.location.id == 987654321


@pytest.mark.asyncio
async def test_pyro_worker_prewarm_dcs():
    mock_client = MagicMock()
    mock_client.media_sessions = {}
    mock_client.storage = AsyncMock()
    mock_client.storage.test_mode.return_value = False
    mock_client.storage.dc_id.return_value = 2  # Current DC is 2

    # Mock Auth and Session
    with patch("app.streamer.pyro_worker.Auth") as MockAuth, \
         patch("app.streamer.pyro_worker.Session") as MockSession:
        
        mock_auth_instance = AsyncMock()
        mock_auth_instance.create.return_value = b"auth_key"
        MockAuth.return_value = mock_auth_instance

        mock_session_instance = AsyncMock()
        MockSession.return_value = mock_session_instance

        mock_exported = MagicMock(id=1, bytes=b"auth_bytes")
        mock_client.invoke = AsyncMock(return_value=mock_exported)

        worker = PyroforkBotWorker(client=mock_client, bot_id=1)
        await worker.prewarm_dcs(target_dcs=[1, 4])

        assert 1 in mock_client.media_sessions
        assert 4 in mock_client.media_sessions
        assert MockSession.call_count == 2
