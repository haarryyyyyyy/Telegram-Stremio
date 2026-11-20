"""Log the Userbot in and out from the dashboard (phone, code, optional 2FA password).

The session string is stored encrypted in the tracking DB. USER_SESSION_STRING in config.env
takes priority at boot. The Userbot only deletes Telegram messages the bots cannot (older than 48 hours).
"""
import secrets
import time

from pyrogram import Client
from pyrogram.errors import (
    BadRequest, FloodWait, PasswordHashInvalid, PhoneCodeExpired, PhoneCodeInvalid,
    PhoneNumberInvalid, SessionPasswordNeeded,
)

import Backend.pyrofork.bot as botmod
from Backend import db
from Backend.config import Telegram
from Backend.helper import task_manager
from Backend.helper.encrypt import decode_string, encode_string
from Backend.logger import LOGGER

_PENDING: dict = {}
_PENDING_TTL = 600


async def _drop(client) -> None:
    try:
        await client.disconnect()
    except Exception:
        pass


async def _cleanup_pending() -> None:
    now = time.time()
    for lid in [k for k, v in _PENDING.items() if now - v["ts"] > _PENDING_TTL]:
        await _drop(_PENDING.pop(lid)["client"])


def _state():
    return db.dbs["tracking"]["state"]


async def get_active_session_string() -> str:
    doc = await _state().find_one({"_id": "user_session"}) or {}
    try:
        return await decode_string(doc["session"]) if doc.get("session") else ""
    except Exception:
        return ""


#----- Start (or restart) the Userbot from a session string. False when Telegram refuses it.
async def activate_userbot(session_string: str) -> bool:
    await deactivate_userbot()
    try:
        await botmod.build_userbot(session_string).start()
        task_manager._not_member.clear()      # a new account may be in channels the old one was not
        LOGGER.info(f"Userbot: [@{botmod.Userbot.me.username or botmod.Userbot.me.id}]")
        return True
    except Exception as e:
        botmod.Userbot = None
        LOGGER.error(f"Userbot did not start: {e}")
        return False


async def deactivate_userbot() -> None:
    if botmod.Userbot is not None:
        try:
            await botmod.Userbot.stop()
        except Exception:
            pass
    botmod.Userbot = None


async def start_login(phone: str) -> dict:
    await _cleanup_pending()
    phone = (phone or "").strip()
    if not phone:
        raise ValueError("Enter your phone number with country code, e.g. +12025550123.")
    if not Telegram.API_ID or not Telegram.API_HASH:
        raise ValueError("API_ID / API_HASH are not configured.")
    client = Client(f"login_{secrets.token_hex(6)}", api_id=Telegram.API_ID, api_hash=Telegram.API_HASH, in_memory=True)
    await client.connect()
    try:
        sent = await client.send_code(phone)
    except (PhoneNumberInvalid, BadRequest):
        await _drop(client)
        raise ValueError("Telegram rejected that phone number. Check the country code.")
    except FloodWait as e:
        await _drop(client)
        raise ValueError(f"Too many attempts. Try again in {e.value} seconds.")
    login_id = secrets.token_hex(12)
    _PENDING[login_id] = {"client": client, "phone": phone, "hash": sent.phone_code_hash, "ts": time.time()}
    return {"login_id": login_id}


def _pending(login_id: str) -> dict:
    entry = _PENDING.get(login_id)
    if not entry:
        raise ValueError("Login expired. Start again.")
    return entry


async def submit_code(login_id: str, code: str) -> dict:
    entry = _pending(login_id)
    try:
        await entry["client"].sign_in(entry["phone"], entry["hash"], (code or "").strip().replace(" ", ""))
    except SessionPasswordNeeded:
        return {"status": "password_needed"}
    except PhoneCodeInvalid:
        raise ValueError("That code is wrong.")
    except PhoneCodeExpired:
        await _drop(_PENDING.pop(login_id)["client"])
        raise ValueError("The code expired. Start again.")
    return await _finalize(login_id)


async def submit_password(login_id: str, password: str) -> dict:
    entry = _pending(login_id)
    try:
        await entry["client"].check_password((password or "").strip())
    except PasswordHashInvalid:
        raise ValueError("Wrong two-step verification password.")
    return await _finalize(login_id)


async def _finalize(login_id: str) -> dict:
    client = _PENDING.pop(login_id)["client"]
    me = await client.get_me()
    session_string = await client.export_session_string()
    await _drop(client)
    name = " ".join(p for p in [me.first_name, me.last_name] if p) or "Telegram User"
    await _state().update_one(
        {"_id": "user_session"},
        {"$set": {"session": await encode_string(session_string), "name": name, "username": me.username or "",
                  "user_id": me.id, "created_at": time.time()}},
        upsert=True,
    )
    if not await activate_userbot(session_string):
        raise ValueError("Logged in, but the Userbot could not start. See log.txt.")
    return {"status": "ok"}


async def get_session_status() -> dict:
    doc = await _state().find_one({"_id": "user_session"}) or {}
    me = getattr(botmod.Userbot, "me", None)
    return {
        "connected": botmod.Userbot is not None,
        "stored": bool(doc.get("session")),
        "from_config": bool(Telegram.USER_SESSION_STRING),
        "name": doc.get("name") or (me and me.first_name) or "",
        "username": doc.get("username") or (me and me.username) or "",
    }


#----- Logout: stop the Userbot and forget the stored session (USER_SESSION_STRING in config.env, if set, is untouched)
async def logout() -> dict:
    await deactivate_userbot()
    await _state().delete_one({"_id": "user_session"})
    return {"ok": True}
