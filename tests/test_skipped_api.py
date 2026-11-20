from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

import Backend
from Backend.fastapi.main import app
from Backend.fastapi.security.credentials import require_auth

app.add_middleware(SessionMiddleware, secret_key="test")  # normally added in __main__ at startup


def _client():
    app.dependency_overrides[require_auth] = lambda: True
    return TestClient(app, follow_redirects=False)


def teardown_function():
    app.dependency_overrides.clear()


def test_page_renders():
    r = _client().get("/admin/skipped")
    assert r.status_code == 200 and "Skipped files" in r.text


def test_list_uses_db(monkeypatch):
    async def fake(status=None, page=1, per_page=50):
        return {"total": 1, "items": [{"_id": "1:2", "chat_id": "1", "msg_id": 2, "file_name": "a.mkv",
                                        "raw_size": 10, "reason": "No title", "status": status or "pending"}]}
    monkeypatch.setattr(Backend.db, "list_skipped_files", fake)
    body = _client().get("/api/admin/skipped?status=pending").json()
    assert body["total"] == 1 and body["items"][0]["id"] == "1:2" and body["items"][0]["reason"] == "No title"


def test_stats_requires_auth():
    r = TestClient(app, follow_redirects=False).get("/stream/stats")
    assert r.status_code == 302 and r.headers["location"] == "/login"   # no stats without an admin session


def test_login_throttle_returns_429():
    from Backend.helper import login_guard
    login_guard.reset()
    c = TestClient(app, follow_redirects=False)
    codes = [c.post("/login", data={"username": "x", "password": "y"}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    login_guard.reset()


import types

from Backend.fastapi.routes import api_routes


async def test_remove_all_deletes_skip_channel_copies_and_every_record(monkeypatch):
    docs = [
        {"_id": "999:1", "chat_id": "999", "msg_id": 1},
        {"_id": "999:2", "chat_id": "999", "msg_id": 2},
        {"_id": "555:7", "chat_id": "555", "msg_id": 7},     # still in a library channel: record goes, message stays
    ]
    deleted_messages, deleted_records = [], []

    async def list_all(status=None, page=1, per_page=50):
        return {"total": len(docs), "items": docs}

    async def delete_many(ids):
        deleted_records.extend(ids)
        return len(ids)

    async def delete_batch(chat_id, ids):
        deleted_messages.append((chat_id, sorted(ids)))
        return []

    monkeypatch.setattr(Backend.db, "list_skipped_files", list_all)
    monkeypatch.setattr(Backend.db, "delete_skipped_files", delete_many, raising=False)
    monkeypatch.setattr(api_routes, "delete_messages_batch", delete_batch)
    monkeypatch.setattr(api_routes, "SettingsManager", types.SimpleNamespace(current=lambda: types.SimpleNamespace(skip_channel="-100999")))

    result = await api_routes._remove_all_skipped_run()
    assert deleted_messages == [(-100999, [1, 2])]                 # only the skip channel is touched
    assert sorted(deleted_records) == ["555:7", "999:1", "999:2"]
    assert result == {"records": 3, "messages": 2, "kept": 1, "failed": 0, "error": ""}


async def test_remove_all_without_a_skip_channel_never_deletes_messages(monkeypatch):
    called = []

    async def list_all(status=None, page=1, per_page=50):
        return {"total": 1, "items": [{"_id": "555:7", "chat_id": "555", "msg_id": 7}]}

    async def delete_many(ids):
        return len(ids)

    async def delete_batch(chat_id, ids):
        called.append(chat_id)
        return []

    monkeypatch.setattr(Backend.db, "list_skipped_files", list_all)
    monkeypatch.setattr(Backend.db, "delete_skipped_files", delete_many, raising=False)
    monkeypatch.setattr(api_routes, "delete_messages_batch", delete_batch)
    monkeypatch.setattr(api_routes, "SettingsManager", types.SimpleNamespace(current=lambda: types.SimpleNamespace(skip_channel="")))
    result = await api_routes._remove_all_skipped_run()
    assert called == [] and result["messages"] == 0 and result["records"] == 1


def test_remove_all_endpoint_needs_login():
    r = TestClient(app, follow_redirects=False).post("/api/admin/skipped/remove-all")
    assert r.status_code in (302, 401)


def test_page_has_a_remove_all_button_and_confirm(monkeypatch):
    r = _client().get("/admin/skipped")
    assert 'id="sk-remove-all"' in r.text and "/api/admin/skipped/remove-all" in r.text and "cannot be undone" in r.text


async def test_remove_all_keeps_records_whose_message_could_not_be_deleted(monkeypatch):
    docs = [{"_id": "999:1", "chat_id": "999", "msg_id": 1}, {"_id": "999:2", "chat_id": "999", "msg_id": 2}]
    removed = []

    async def list_all(status=None, page=1, per_page=50):
        return {"total": 2, "items": docs}

    async def delete_many(ids):
        removed.extend(ids)
        return len(ids)

    async def delete_batch(chat_id, ids):
        return [2]

    monkeypatch.setattr(Backend.db, "list_skipped_files", list_all)
    monkeypatch.setattr(Backend.db, "delete_skipped_files", delete_many, raising=False)
    monkeypatch.setattr(api_routes, "delete_messages_batch", delete_batch)
    monkeypatch.setattr(api_routes.task_manager, "last_delete_error", "MessageDeleteForbidden: no rights")
    monkeypatch.setattr(api_routes, "SettingsManager", types.SimpleNamespace(current=lambda: types.SimpleNamespace(skip_channel="-100999")))
    result = await api_routes._remove_all_skipped_run()
    assert removed == ["999:1"]                              # 999:2 stays in the list so it can be retried
    assert result["failed"] == 1 and "MessageDeleteForbidden" in result["error"]
