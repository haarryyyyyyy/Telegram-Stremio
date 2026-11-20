import os
import time

import pytest

from Backend.helper import chunk_cache as cc

MB = 1024 * 1024


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cc, "LIMIT_BYTES", 3 * MB)
    monkeypatch.setattr(cc, "_puts", 0)
    return tmp_path


def test_only_the_start_and_end_of_a_file_are_cached():
    size = 100 * MB
    assert cc.wanted(0, MB, size) and cc.wanted(3 * MB, MB, size)              # head
    assert cc.wanted(99 * MB, MB, size) and cc.wanted(96 * MB, MB, size)       # tail
    assert not cc.wanted(50 * MB, MB, size)                                    # middle
    assert not cc.wanted(0, MB, 0)                                             # unknown size


async def test_put_then_get_returns_the_same_bytes(cache):
    await cc.put("AgADBQ-x_1", 0, MB, b"abc")
    assert await cc.get("AgADBQ-x_1", 0, MB) == b"abc"
    assert await cc.get("AgADBQ-x_1", MB, MB) is None


async def test_unsafe_ids_are_never_used_as_paths(cache):
    await cc.put("../../etc", 0, MB, b"x")
    assert not any(cache.iterdir()) and await cc.get("../../etc", 0, MB) is None


async def test_least_recently_used_chunks_go_first_when_over_the_limit(cache):
    for i, name in enumerate(["a", "b", "c", "d"]):
        await cc.put(name, 0, MB, b"x" * MB)
        os.utime(cache / f"{name}_0_{MB}.bin", (time.time() - 100 + i, time.time() - 100 + i))
    await cc.get("a", 0, MB)                    # touching "a" makes it the newest
    cc.trim()
    left = sorted(p.name.split("_")[0] for p in cache.iterdir())
    assert left == ["a", "c", "d"]


async def test_empty_reads_are_not_cached(cache):
    await cc.put("e", 0, MB, b"")
    assert not any(cache.iterdir())


async def test_a_replayed_stream_start_comes_from_disk_not_telegram(cache, monkeypatch):
    import asyncio
    import types

    from Backend.helper import custom_dl
    from Backend.pyrofork.bot import work_loads

    sends = []

    class Session:
        async def send(self, req):
            sends.append(req.offset)
            return types.SimpleNamespace(bytes=bytes([req.offset // MB % 256]) * MB)

    streamer = object.__new__(custom_dl.ByteStreamer)
    streamer.client, streamer.client_index = types.SimpleNamespace(media_sessions={}), 0

    async def media_session(_fid):
        return Session()

    async def location(_fid):
        return "loc"
    monkeypatch.setattr(streamer, "_get_media_session", media_session, raising=False)
    monkeypatch.setattr(custom_dl.ByteStreamer, "_get_location", staticmethod(location))
    work_loads[0] = 0
    fid = types.SimpleNamespace(dc_id=4, unique_id="AgADtest", file_size=50 * MB, local_id=1, chat_id=1)

    async def play():
        gen = await streamer.prefetch_stream(fid, 0, 0, 0, MB, 2, MB, 1, 1)
        return b"".join([c async for c in gen])

    first = await play()
    await asyncio.sleep(0.05)              # cache writes run in the background
    sends.clear()
    second = await play()
    assert second == first and sends == []
