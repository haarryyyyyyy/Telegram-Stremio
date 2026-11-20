from asyncio import sleep
from typing import List

from pyrogram.errors import (
    FloodWait,
    ChatAdminRequired,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageAuthorRequired,
    PeerIdInvalid,
    UserNotParticipant,
    AuthKeyUnregistered,
    SessionRevoked,
    RPCError,
)
from pyrogram.enums import ParseMode

from Backend.logger import LOGGER
from Backend.pyrofork.bot import StreamBot, multi_clients

DELETE_BATCH_SIZE = 10
_FALLBACK_WORTHY = (
    ChatAdminRequired,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageAuthorRequired,
    UserNotParticipant,
    RPCError,
)
_SESSION_DEAD = (AuthKeyUnregistered, SessionRevoked)
PROBE_SINGLES = 3
last_delete_error = ""   # the most recent Telegram reason a delete failed, shown on the Skipped page


def _note(error) -> None:
    global last_delete_error
    last_delete_error = f"{type(error).__name__}: {error}"

async def _resolve_peer(client, chat_id) -> bool:
    try:
        await client.get_chat(chat_id)
        return True
    except Exception:
        return False


async def edit_message(chat_id: int, msg_id: int, new_caption: str):
    try:
        await StreamBot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=new_caption, parse_mode=ParseMode.HTML)
        await sleep(2)
        return
    except FloodWait as e:
        LOGGER.warning(f"FloodWait for {e.value}s while editing message {msg_id} in {chat_id}")
        await sleep(e.value)
        try:
            await StreamBot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=new_caption, parse_mode=ParseMode.HTML)
            return
        except Exception as e2:
            LOGGER.error(f"Retry after FloodWait failed while editing {msg_id} in {chat_id}: {e2}")
    except PeerIdInvalid as e:
        if await _resolve_peer(StreamBot, chat_id):
            try:
                await StreamBot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=new_caption, parse_mode=ParseMode.HTML)
                return
            except Exception as e2:
                LOGGER.error(f"Retry after peer resolve failed while editing {msg_id} in {chat_id}: {e2}")
        LOGGER.error(f"Error while editing message {msg_id} in {chat_id}: {e}")
    except _FALLBACK_WORTHY as e:
        LOGGER.error(f"Error while editing message {msg_id} in {chat_id}: {e}")
    except Exception as e:
        LOGGER.error(f"Error while editing message {msg_id} in {chat_id}: {e}")


async def delete_message(chat_id: int, msg_id: int):
    await delete_messages_batch(chat_id, [msg_id])


async def delete_messages_batch(chat_id: int, msg_ids: List[int]) -> List[int]:
    """Delete messages, falling back to every other bot: the bot that posted a copy can always delete it,
    even without the channel's "Delete messages" right. Returns the ids no bot could delete."""
    failed: List[int] = []
    for i in range(0, len(msg_ids or []), DELETE_BATCH_SIZE):
        chunk = msg_ids[i:i + DELETE_BATCH_SIZE]

        remaining = await _delete_with(StreamBot, "StreamBot", chat_id, chunk)
        for idx, client in list(multi_clients.items()):
            if not remaining:
                break
            if client is not StreamBot:
                remaining = await _delete_with(client, f"Bot{idx}", chat_id, remaining)

        if remaining:
            LOGGER.error(f"Could not delete {len(remaining)} message(s) in {chat_id}: {last_delete_error}")
            failed += remaining

        await sleep(1)
    return failed


#----- Telegram rejects a whole batch when any one id cannot be deleted (MESSAGE_DELETE_FORBIDDEN, e.g. a
#----- service message). After a failed batch, delete one by one so only the bad ids stay.
async def _delete_with(client, label: str, chat_id: int, msg_ids: List[int]) -> List[int]:
    remaining = await _delete_chunk(client, label, chat_id, msg_ids)
    if len(remaining) <= 1:
        return remaining
    left = []
    for n, mid in enumerate(remaining):
        failed = await _delete_chunk(client, label, chat_id, [mid])
        left += failed
        #----- The first few all failing means this bot cannot delete any of them (Telegram's 48-hour limit
        #----- for bots, or no rights): stop instead of one refused call per message.
        if n == PROBE_SINGLES - 1 and len(left) == PROBE_SINGLES:
            return left + remaining[PROBE_SINGLES:]
        await sleep(0.05)
    return left


#----- One line per bot: is it an admin of the chat, and may it delete messages there
async def delete_rights_report(chat_id: int) -> str:
    lines = []
    for idx, client in list(multi_clients.items()):
        name = "@" + (getattr(getattr(client, "me", None), "username", None) or f"bot{idx}")
        try:
            m = await client.get_chat_member(chat_id, "me")
        except Exception as e:
            lines.append(f"{name}: not reachable ({e})")
            continue
        status = getattr(getattr(m, "status", None), "name", str(getattr(m, "status", ""))).lower()
        can = bool(getattr(getattr(m, "privileges", None), "can_delete_messages", False))
        lines.append(f"{name}: {status}, {'can delete' if can else 'cannot delete'}")
    return "; ".join(lines)


async def _delete_chunk(client, client_label: str, chat_id: int, msg_ids: List[int]) -> List[int]:
    try:
        await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
        LOGGER.info(f"[{client_label.upper()}] Deleted {len(msg_ids)} message(s) in {chat_id}")
        return []
    except FloodWait as e:
        LOGGER.warning(f"[{client_label.upper()}] FloodWait detected: sleeping {e.value}s ({len(msg_ids)} msg(s) in {chat_id})")
        await sleep(e.value)
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
            LOGGER.info(f"[{client_label.upper()}] Deleted {len(msg_ids)} message(s) in {chat_id} after FloodWait retry")
            return []
        except Exception as e2:
            LOGGER.error(f"[{client_label.upper()}] Retry after FloodWait failed in {chat_id}: {e2}")
            return msg_ids
    except PeerIdInvalid as e:
        if await _resolve_peer(client, chat_id):
            try:
                await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
                LOGGER.info(f"[{client_label.upper()}] Deleted {len(msg_ids)} message(s) in {chat_id} after peer resolve")
                return []
            except Exception as e2:
                LOGGER.error(f"[{client_label.upper()}] Retry after peer resolve failed in {chat_id}: {e2}")
                return msg_ids
        LOGGER.warning(f"[{client_label.upper()}] Peer unresolved in {chat_id}: {e}")
        _note(e)
        return msg_ids
    except _SESSION_DEAD as e:
        LOGGER.error(f"[{client_label.upper()}] Session invalid ({type(e).__name__}): {e}")
        _note(e)
        return msg_ids
    except _FALLBACK_WORTHY as e:
        LOGGER.warning(f"[{client_label.upper()}] Cannot delete in {chat_id} ({type(e).__name__}): {e}")
        _note(e)
        return msg_ids
    except Exception as e:
        LOGGER.error(f"[{client_label.upper()}] Unexpected error deleting in {chat_id}: {e}")
        _note(e)
        return msg_ids
