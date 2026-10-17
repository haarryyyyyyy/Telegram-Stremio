import asyncio
from abc import ABC, abstractmethod
from typing import List, AsyncIterator, Dict, Any, Optional


class BotWorker(ABC):
    @abstractmethod
    async def fetch_chunk(self, file_id: str, offset: int, limit: int) -> bytes:
        """Fetch a single byte chunk from Telegram."""
        pass


class StreamMultiplexer:
    def __init__(self, bots: List[BotWorker], prefetch_window: int = 8):
        if not bots:
            raise ValueError("StreamMultiplexer requires at least one BotWorker")
        self.bots = bots
        self.prefetch_window = prefetch_window

    async def stream_range(
        self,
        file_id: str,
        start: int,
        end: int,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        """
        Concurrently stripes chunk downloads across all available bots and yields
        chunks in strict sequential order.
        """
        total_bytes = end - start + 1
        num_chunks = (total_bytes + chunk_size - 1) // chunk_size

        ready_chunks: Dict[int, bytes] = {}
        pending_tasks: Dict[int, asyncio.Task] = {}
        next_to_schedule = 0
        next_to_yield = 0

        # Concurrency limit based on bot count and prefetch window
        max_concurrent = min(len(self.bots) * 2, self.prefetch_window)

        async def _fetch_with_worker(chunk_idx: int, bot_idx: int, off: int, lim: int) -> tuple[int, bytes]:
            # Try primary assigned bot, failover to subsequent bots on error
            for attempt in range(len(self.bots)):
                current_bot = self.bots[(bot_idx + attempt) % len(self.bots)]
                try:
                    data = await current_bot.fetch_chunk(file_id, off, lim)
                    return chunk_idx, data
                except Exception:
                    if attempt == len(self.bots) - 1:
                        raise
                    await asyncio.sleep(0.01)
            raise RuntimeError(f"All available bots failed for chunk {chunk_idx}")

        while next_to_yield < num_chunks:
            # Schedule new chunk tasks up to max_concurrent / prefetch limit
            while (
                len(pending_tasks) < max_concurrent
                and next_to_schedule < num_chunks
                and (next_to_schedule - next_to_yield) < self.prefetch_window
            ):
                idx = next_to_schedule
                bot_idx = idx % len(self.bots)
                chunk_offset = start + (idx * chunk_size)
                chunk_limit = min(chunk_size, (end - chunk_offset + 1))

                task = asyncio.create_task(_fetch_with_worker(idx, bot_idx, chunk_offset, chunk_limit))
                pending_tasks[idx] = task
                next_to_schedule += 1

            if not pending_tasks and next_to_yield not in ready_chunks:
                break

            # If the very next chunk is already downloaded, yield it immediately without waiting!
            if next_to_yield in ready_chunks:
                data = ready_chunks.pop(next_to_yield)
                yield data
                next_to_yield += 1
                continue

            # Wait for any scheduled chunk to complete
            done, _ = await asyncio.wait(pending_tasks.values(), return_when=asyncio.FIRST_COMPLETED)
            for completed_task in done:
                # Find which chunk index completed
                chunk_idx, data = await completed_task
                pending_tasks.pop(chunk_idx, None)
                ready_chunks[chunk_idx] = data

            # Yield sequential ready chunks
            while next_to_yield in ready_chunks:
                data = ready_chunks.pop(next_to_yield)
                yield data
                next_to_yield += 1
