import asyncio

import Backend


async def test_concurrent_inserts_are_serialised(monkeypatch):
    # Receiver, channel scan, manual add and Skipped retry each used their own lock (or none) around the same
    # read-modify-write of a show document; two at once could drop one episode.
    db = Backend.db
    running, overlaps = [0], []

    async def slow_insert(*_a, **_k):
        running[0] += 1
        overlaps.append(running[0])
        await asyncio.sleep(0.01)
        running[0] -= 1
        return None

    monkeypatch.setattr(db, "_insert_media", slow_insert)
    await asyncio.gather(*(db.insert_media({}, channel=1, msg_id=i, size="1", name="x") for i in range(5)))
    assert max(overlaps) == 1
