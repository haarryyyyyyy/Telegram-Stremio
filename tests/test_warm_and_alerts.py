import types

import pytest

from Backend.fastapi.routes import stream_routes
from Backend.helper import chunk_cache, owner_alerts


class _Streamer:
    def __init__(self):
        self.calls = []

    async def prefetch_stream(self, **kw):
        self.calls.append(kw)

        async def body():
            yield b"x"
        return body()


@pytest.fixture
def warm(monkeypatch):
    streamer = _Streamer()
    fid = types.SimpleNamespace(unique_id="AgADxyz", file_size=5 * 1024 * 1024)

    async def decode(s):
        return {"parts": [1, 2]} if s == "split" else {"chat_id": "123", "msg_id": 7}

    async def db_client(fetch):
        return 0, streamer, fid

    async def title(h, n):
        return "The Odyssey"

    monkeypatch.setattr(stream_routes, "decode_string", decode)
    monkeypatch.setattr(stream_routes, "_db_client", db_client)
    monkeypatch.setattr(stream_routes, "_lookup_title", title)
    monkeypatch.setattr(stream_routes, "_warmed", {})
    monkeypatch.setattr(chunk_cache, "LIMIT_BYTES", 1024 ** 3)
    monkeypatch.setattr(chunk_cache, "has", lambda uid, off, lim: False)
    return streamer


async def test_warm_fetches_the_first_megabyte_once(warm):
    await stream_routes.warm_first_chunk("abc", "ann")
    await stream_routes.warm_first_chunk("abc", "ann")          # Stremio asks for the list again: no second fetch
    assert len(warm.calls) == 1
    call = warm.calls[0]
    assert call["offset"] == 0 and call["part_count"] == 1 and call["chunk_size"] == 1024 * 1024
    assert call["meta"] == {"title": "The Odyssey", "user_name": "ann", "internal": True}


async def test_warm_skips_split_files_and_cached_starts(warm, monkeypatch):
    await stream_routes.warm_first_chunk("split")
    monkeypatch.setattr(chunk_cache, "has", lambda uid, off, lim: True)
    await stream_routes.warm_first_chunk("cached")
    assert warm.calls == []


async def test_warm_is_off_when_the_cache_is_off(warm, monkeypatch):
    monkeypatch.setattr(chunk_cache, "LIMIT_BYTES", 0)
    await stream_routes.warm_first_chunk("abc")
    assert warm.calls == []


def _report(bot2=True, usage=40, userbot="ok"):
    return {"sections": [
        {"key": "databases", "items": [{"name": "storage_1", "status": "ok", "usage_pct": usage}]},
        {"key": "bots", "items": [{"name": "Bot 1", "connected": True}, {"name": "Bot 2", "connected": bot2}]},
        {"key": "userbot", "label": "Userbot", "status": userbot, "message": "Can delete in 1 of 2 channels.",
         "items": [{"name": "Movies", "can_delete": True}, {"name": "Skip", "can_delete": False}]},
    ]}


def test_alerts_only_send_what_changed(monkeypatch):
    monkeypatch.setattr(owner_alerts, "_open", {})
    facts = {"disk_total": 100, "disk_free": 50}
    assert owner_alerts.changes(owner_alerts.problems(_report(), facts)) == ""

    text = owner_alerts.changes(owner_alerts.problems(_report(bot2=False, usage=93, userbot="degraded"), facts))
    assert "Bot 2 is disconnected." in text and "storage_1 is 93% full" in text and "Cannot delete in: Skip." in text

    # still broken, the % moved: nothing new to say
    assert owner_alerts.changes(owner_alerts.problems(_report(bot2=False, usage=95, userbot="degraded"), facts)) == ""

    text = owner_alerts.changes(owner_alerts.problems(_report(usage=95, userbot="degraded"), {"disk_total": 100, "disk_free": 5}))
    assert text.startswith("Telegram-Stremio needs attention:\n- Disk almost full")
    assert "Fixed:\n- Bot 2 is disconnected." in text


async def test_check_once_sends_through_the_given_sender(monkeypatch):
    monkeypatch.setattr(owner_alerts, "_open", {})
    sent = []

    async def report(force=False):
        return _report(bot2=False)

    async def send(text):
        sent.append(text)

    monkeypatch.setattr(owner_alerts.health, "run_health_checks", report)
    monkeypatch.setattr(owner_alerts.server_load, "snapshot", lambda: {"facts": {}})
    await owner_alerts.check_once(send)
    await owner_alerts.check_once(send)
    assert len(sent) == 1 and "Bot 2" in sent[0]
