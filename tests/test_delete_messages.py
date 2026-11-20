from pyrogram.errors import MessageDeleteForbidden

from Backend.helper import task_manager


class Bot:
    def __init__(self, allowed):
        self.allowed, self.calls = set(allowed), []

    async def delete_messages(self, chat_id, message_ids):
        self.calls.append(list(message_ids))
        if not set(message_ids) <= self.allowed:
            raise MessageDeleteForbidden()


async def test_another_bot_deletes_what_the_main_bot_cannot(monkeypatch):
    main, poster = Bot(allowed=[]), Bot(allowed=[1, 2])
    monkeypatch.setattr(task_manager, "StreamBot", main)
    monkeypatch.setattr(task_manager, "multi_clients", {0: main, 3: poster})
    monkeypatch.setattr(task_manager, "sleep", _no_sleep)
    failed = await task_manager.delete_messages_batch(-100999, [1, 2])
    assert failed == [] and poster.calls == [[1, 2]]


async def test_messages_no_bot_can_delete_are_returned(monkeypatch):
    main = Bot(allowed=[])
    monkeypatch.setattr(task_manager, "StreamBot", main)
    monkeypatch.setattr(task_manager, "multi_clients", {0: main})
    monkeypatch.setattr(task_manager, "sleep", _no_sleep)
    assert await task_manager.delete_messages_batch(-100999, [5]) == [5]
    assert "MessageDeleteForbidden" in task_manager.last_delete_error


async def _no_sleep(*_a):
    return None


import types


class PickyBot(Bot):
    """Telegram rejects the whole batch when one id cannot be deleted (e.g. a service message)."""


async def test_one_bad_id_does_not_block_the_rest_of_the_batch(monkeypatch):
    bot = PickyBot(allowed=[1, 2, 4])
    monkeypatch.setattr(task_manager, "StreamBot", bot)
    monkeypatch.setattr(task_manager, "multi_clients", {0: bot})
    monkeypatch.setattr(task_manager, "sleep", _no_sleep)
    assert await task_manager.delete_messages_batch(-100999, [1, 2, 3, 4]) == [3]


async def test_rights_report_names_each_bot_and_its_delete_right(monkeypatch):
    def member(status, can_delete):
        return types.SimpleNamespace(status=types.SimpleNamespace(name=status),
                                     privileges=types.SimpleNamespace(can_delete_messages=can_delete) if can_delete is not None else None)

    class B:
        def __init__(self, uname, m):
            self.me, self._m = types.SimpleNamespace(username=uname), m

        async def get_chat_member(self, chat_id, user):
            if isinstance(self._m, Exception):
                raise self._m
            return self._m

    monkeypatch.setattr(task_manager, "multi_clients", {
        0: B("main_bot", member("ADMINISTRATOR", True)),
        1: B("helper_bot", member("MEMBER", None)),
        2: B("gone_bot", RuntimeError("CHANNEL_PRIVATE")),
    })
    report = await task_manager.delete_rights_report(-100999)
    assert "@main_bot: administrator, can delete" in report
    assert "@helper_bot: member, cannot delete" in report
    assert "@gone_bot: not reachable (CHANNEL_PRIVATE)" in report
