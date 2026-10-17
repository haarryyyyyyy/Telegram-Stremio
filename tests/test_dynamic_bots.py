import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.streamer.pyro_worker import BotPoolManager
from app.streamer.multiplexer import StreamMultiplexer


@pytest.mark.asyncio
async def test_bot_pool_dynamic_add_and_remove():
    with patch("app.streamer.pyro_worker.Client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value = mock_instance

        pool = BotPoolManager(api_id=12345, api_hash="hash", bot_tokens=["tok1", "tok2"])
        await pool.start_all(prewarm=False)
        assert len(pool.get_workers()) == 2

        mux = StreamMultiplexer(bots=pool.get_workers())
        assert len(mux.bots) == 2

        # 1. Dynamically add a 3rd bot
        with patch("app.streamer.pyro_worker.PyroforkBotWorker.prewarm_dcs", AsyncMock()):
            worker = await pool.add_bot("tok3", prewarm=False)
            assert worker is not None
            assert len(pool.get_workers()) == 3
            
            # Sync with multiplexer
            mux.update_bots(pool.get_workers())
            assert len(mux.bots) == 3

        # 2. Dynamically remove a bot
        removed = await pool.remove_bot("tok1")
        assert removed is True
        assert len(pool.get_workers()) == 2
        mux.update_bots(pool.get_workers())
        assert len(mux.bots) == 2
