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


async def test_userbot_health_reports_rights_per_channel(monkeypatch):
    from Backend.helper import task_manager
    from Backend.helper.settings_manager import Settings, SettingsManager

    class User:
        is_connected = True
        me = types.SimpleNamespace(username="ub", first_name="U")

        async def get_chat_member(self, chat, who):
            can = chat == -1001
            return types.SimpleNamespace(privileges=types.SimpleNamespace(can_delete_messages=can))

    async def peer(client, chat_id):
        return chat_id != -1003

    monkeypatch.setattr(botmod, "Userbot", User())
    monkeypatch.setattr(task_manager, "ensure_peer", peer)
    monkeypatch.setattr(SettingsManager, "_current", Settings({"auth_channels": ["-1001", "-1002"], "skip_channel": "3",
                                                               "channel_titles": {"-1001": "Movies"}}))
    r = await health._check_userbot()
    by = {i["name"]: i for i in r["items"]}
    assert by["Movies"]["can_delete"] is True
    assert by["-1002"]["message"] == "no Delete messages right"
    assert by["3"]["message"] == "not a member"
    assert r["status"] == "degraded" and "1 of 3" in r["message"]
