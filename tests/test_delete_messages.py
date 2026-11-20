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
