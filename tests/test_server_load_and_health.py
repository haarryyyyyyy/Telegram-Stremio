import types

from Backend.helper import health, server_load
from Backend.pyrofork import bot as botmod

STAT = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3\n"
MEMINFO = "MemTotal:        1000 kB\nMemAvailable:     250 kB\nSwapTotal:        0 kB\n"
NETDEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0
  ens3: 1000 5 0 0 0 0 0 0 4000 7 0 0 0 0 0 0
"""


def test_proc_parsers():
    assert server_load.cpu_times(STAT) == (200, 1000)          # busy excludes idle and iowait
    mem = server_load.meminfo(MEMINFO)
    assert mem["MemTotal"] == 1000 * 1024 and mem["MemAvailable"] == 250 * 1024
    assert server_load.net_bytes(NETDEV) == (1000, 4000)       # loopback is left out
    assert server_load.cpu_times("") is None and server_load.net_bytes("") is None


def test_sample_keeps_history_bounded(monkeypatch):
    server_load.history.clear()
    for _ in range(server_load.history.maxlen + 5):
        server_load.sample()
    assert len(server_load.history) == server_load.history.maxlen
    assert {"cpu", "mem", "rx", "tx", "lag", "streams", "bot_load"} <= set(server_load.history[-1])
    assert server_load.snapshot()["now"] is server_load.history[-1]


async def test_internal_reads_are_not_saved_as_streams(monkeypatch):
    from Backend import db
    saved = []

    class Coll:
        async def insert_one(self, doc):
            saved.append(doc)

        async def update_one(self, *a, **k):
            pass

    monkeypatch.setattr(db, "dbs", {"tracking": {"stream_analytics": Coll(), "user_activity": Coll()}}, raising=False)
    await db.log_stream_stats({"meta": {"title": "The Odyssey", "user_name": "ann", "internal": True}})
    assert saved == []
    await db.log_stream_stats({"meta": {"title": "The Odyssey", "user_name": "ann"}})
    assert saved[0]["title"] == "The Odyssey" and saved[0]["user_name"] == "ann"


async def test_userbot_health_not_logged_in(monkeypatch):
    monkeypatch.setattr(botmod, "Userbot", None)
    r = await health._check_userbot()
    assert r["status"] == "not_configured" and "Settings" in r["message"]


class _User:
    is_connected = True
    me = types.SimpleNamespace(username="ub", first_name="U")

    def __init__(self):
        self.dialog_scans = 0

    async def get_chat_member(self, chat, who):
        if chat == -1003:
            raise ValueError("Peer id invalid")       # unknown to a fresh session, and not in its chats
        return types.SimpleNamespace(privileges=types.SimpleNamespace(can_delete_messages=chat == -1001))

    async def get_dialogs(self):
        self.dialog_scans += 1
        for cid in (-1001, -1002):
            yield types.SimpleNamespace(chat=types.SimpleNamespace(id=cid))


def _settings(monkeypatch):
    from Backend.helper.settings_manager import Settings, SettingsManager
    monkeypatch.setattr(SettingsManager, "_current", Settings({"auth_channels": ["-1001", "-1002"], "skip_channel": "3",
                                                               "channel_titles": {"-1001": "Movies"}}))


async def test_userbot_health_reports_rights_per_channel(monkeypatch):
    user = _User()
    monkeypatch.setattr(botmod, "Userbot", user)
    _settings(monkeypatch)
    r = await health._check_userbot()
    by = {i["name"]: i for i in r["items"]}
    assert by["Movies"]["can_delete"] is True
    assert by["-1002"]["message"] == "no Delete messages right"
    assert by["3"]["message"] == "not a member"
    assert r["status"] == "degraded" and "1 of 3" in r["message"]
    assert user.dialog_scans == 1                      # the chat list is read once, not once per channel


async def test_health_report_never_waits_for_the_userbot(monkeypatch):
    import asyncio
    monkeypatch.setattr(botmod, "Userbot", _User())
    _settings(monkeypatch)
    monkeypatch.setattr(health, "_userbot", {"result": None, "at": -1e9, "task": None})
    first = health._userbot_status()
    assert first["status"] == "checking"               # answered at once; the check runs in the background
    await health._userbot["task"]
    assert health._userbot_status()["status"] == "degraded"
    await asyncio.sleep(0)
