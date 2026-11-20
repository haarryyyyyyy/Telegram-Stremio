import types

import pytest

from Backend.helper import session_auth
from Backend.pyrofork import bot as botmod


class Coll:
    def __init__(self, doc=None):
        self.doc = doc
        self.saved = None

    async def find_one(self, q):
        return self.doc

    async def update_one(self, q, update, upsert=False):
        self.saved = update["$set"]
        self.doc = {**(self.doc or {}), **self.saved}

    async def delete_one(self, q):
        self.doc = None


class FakeUser:
    stopped = False

    async def stop(self):
        self.stopped = True


@pytest.fixture
def coll(monkeypatch):
    c = Coll()
    monkeypatch.setattr(session_auth.db, "dbs", {"tracking": {"state": c}}, raising=False)
    monkeypatch.setattr(botmod, "Userbot", None)
    return c


async def test_empty_phone_is_rejected(coll):
    with pytest.raises(ValueError):
        await session_auth.start_login("  ")


async def test_expired_login_is_rejected(coll):
    with pytest.raises(ValueError):
        await session_auth.submit_code("nope", "12345")


async def test_status_logged_out(coll):
    st = await session_auth.get_session_status()
    assert st["connected"] is False and st["stored"] is False


async def test_logout_stops_the_userbot_and_forgets_the_session(coll, monkeypatch):
    user = FakeUser()
    monkeypatch.setattr(botmod, "Userbot", user)
    coll.doc = {"session": "x", "name": "A"}
    await session_auth.logout()
    assert user.stopped and botmod.Userbot is None and coll.doc is None


async def test_finalize_stores_the_session_encrypted_and_starts_the_userbot(coll, monkeypatch):
    class Login:
        async def get_me(self):
            return types.SimpleNamespace(first_name="Ann", last_name=None, username="ann", id=7)

        async def export_session_string(self):
            return "RAW-SESSION"

        async def disconnect(self):
            pass

    started = []

    async def activate(s):
        started.append(s)
        return True

    session_auth._PENDING["l1"] = {"client": Login(), "phone": "+1", "hash": "h", "ts": 0}
    monkeypatch.setattr(session_auth, "activate_userbot", activate)
    assert await session_auth._finalize("l1") == {"status": "ok"}
    assert started == ["RAW-SESSION"]
    assert coll.saved["session"] != "RAW-SESSION" and coll.saved["username"] == "ann"
    assert await session_auth.get_active_session_string() == "RAW-SESSION"
