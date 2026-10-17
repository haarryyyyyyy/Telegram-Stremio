import pytest
import asyncio
from typing import List
from app.streamer.multiplexer import StreamMultiplexer, BotWorker


class MockBotWorker(BotWorker):
    def __init__(self, bot_id: int, delay: float = 0.01):
        self.bot_id = bot_id
        self.delay = delay
        self.fetched_offsets: List[int] = []

    async def fetch_chunk(self, file_id: str, offset: int, limit: int) -> bytes:
        self.fetched_offsets.append(offset)
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return f"CHUNK_{offset}_{limit}".encode()


@pytest.mark.asyncio
async def test_stream_chunks_concurrent_striping_in_order():
    bots = [MockBotWorker(bot_id=i) for i in range(3)]
    mux = StreamMultiplexer(bots=bots, prefetch_window=4)

    file_id = "test_file_id"
    chunk_size = 1024  # 1 KB for test
    start_byte = 0
    end_byte = (chunk_size * 3) - 1  # 3 full chunks: 0, 1024, 2048

    received_chunks = []
    async for chunk in mux.stream_range(file_id=file_id, start=start_byte, end=end_byte, chunk_size=chunk_size):
        received_chunks.append(chunk)

    # 1. Verify in-order delivery
    assert len(received_chunks) == 3
    assert received_chunks[0] == b"CHUNK_0_1024"
    assert received_chunks[1] == b"CHUNK_1024_1024"
    assert received_chunks[2] == b"CHUNK_2048_1024"

    # 2. Verify all 3 bots participated in parallel striping
    participating_bots = [b for b in bots if len(b.fetched_offsets) > 0]
    assert len(participating_bots) == 3


class FailingBotWorker(BotWorker):
    def __init__(self, bot_id: int, fail_once: bool = False):
        self.bot_id = bot_id
        self.fail_once = fail_once
        self.has_failed = False

    async def fetch_chunk(self, file_id: str, offset: int, limit: int) -> bytes:
        if self.fail_once and not self.has_failed:
            self.has_failed = True
            raise ConnectionError(f"Simulated Telegram disconnect on bot {self.bot_id}")
        return f"CHUNK_{offset}_{limit}".encode()


@pytest.mark.asyncio
async def test_stream_chunks_failover_on_bot_error():
    # Bot 1 will fail on its first request, Bot 0 and Bot 2 are healthy
    bots = [
        FailingBotWorker(bot_id=0),
        FailingBotWorker(bot_id=1, fail_once=True),
        FailingBotWorker(bot_id=2),
    ]
    mux = StreamMultiplexer(bots=bots, prefetch_window=4)

    file_id = "test_file_id"
    chunk_size = 1024
    start_byte = 0
    end_byte = (chunk_size * 3) - 1

    received_chunks = []
    async for chunk in mux.stream_range(file_id=file_id, start=start_byte, end=end_byte, chunk_size=chunk_size):
        received_chunks.append(chunk)

    # All 3 chunks must still be delivered accurately despite the failure
    assert len(received_chunks) == 3
    assert received_chunks[0] == b"CHUNK_0_1024"
    assert received_chunks[1] == b"CHUNK_1024_1024"
    assert received_chunks[2] == b"CHUNK_2048_1024"


class VariableDelayBotWorker(BotWorker):
    def __init__(self, bot_id: int):
        self.bot_id = bot_id

    async def fetch_chunk(self, file_id: str, offset: int, limit: int) -> bytes:
        # Chunk 0 takes 10ms, but subsequent chunks take 100ms
        delay = 0.01 if offset == 0 else 0.1
        await asyncio.sleep(delay)
        return f"CHUNK_{offset}_{limit}".encode()


@pytest.mark.asyncio
async def test_stream_fast_start_immediate_delivery():
    import time
    bots = [VariableDelayBotWorker(bot_id=i) for i in range(2)]
    mux = StreamMultiplexer(bots=bots, prefetch_window=4)

    start_time = time.perf_counter()
    first_chunk = None

    async for chunk in mux.stream_range(file_id="test", start=0, end=2047, chunk_size=1024):
        first_chunk = chunk
        time_to_first_chunk = time.perf_counter() - start_time
        break

    assert first_chunk == b"CHUNK_0_1024"
    # First chunk must arrive in under 50ms, unaffected by slower subsequent chunks
    assert time_to_first_chunk < 0.05
