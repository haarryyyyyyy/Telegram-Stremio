"""Message the owner (OWNER_ID) on Telegram when something breaks, and again when it is fixed.

Every CHECK_EVERY seconds it reads the same health report as the Admin page plus the disk space, and sends
only what changed since the last check, so a problem that lasts a day is one message, not hundreds.
"""
import asyncio

from Backend.config import Telegram
from Backend.helper import health, server_load
from Backend.logger import LOGGER

CHECK_EVERY = 300
DB_FULL_PCT = 90          # Atlas free tier holds 512 MB per database
DISK_FREE_PCT = 10
_open: dict = {}          # problem key -> message last sent


def _gb(n) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


def problems(report: dict, facts: dict) -> dict:
    """{key: message} for everything wrong right now. Keys stay stable while values (like a %) change."""
    out = {}
    for sec in report.get("sections", []):
        key = sec.get("key")
        if key == "databases":
            for db in sec.get("items", []):
                name = db.get("name")
                if db.get("status") != "ok":
                    out[f"db:{name}"] = f"Database {name} is unreachable: {db.get('message') or 'no answer'}"
                elif (db.get("usage_pct") or 0) >= DB_FULL_PCT:
                    out[f"dbfull:{name}"] = (f"Database {name} is {db['usage_pct']}% full. New files go to the next "
                                             "database when it fills; add one in Settings if this is the last.")
        elif key == "bots":
            for bot in sec.get("items", []):
                if not bot.get("connected"):
                    out[f"bot:{bot.get('name')}"] = f"{bot.get('name')} is disconnected."
        elif key in ("tmdb", "base_url", "userbot") and sec.get("status") in ("error", "down", "degraded"):
            missing = [i["name"] for i in sec.get("items") or [] if not i.get("can_delete")]
            extra = f" Cannot delete in: {', '.join(missing)}." if missing else ""
            out[key] = f"{sec.get('label')}: {sec.get('message', '')}{extra}"
    total, free = facts.get("disk_total"), facts.get("disk_free")
    if total and free is not None and 100 * free / total < DISK_FREE_PCT:
        out["disk"] = f"Disk almost full: {_gb(free)} free of {_gb(total)}."
    return out


def changes(current: dict) -> str:
    """The message to send for what appeared and what cleared since the last check ('' when nothing changed)."""
    new = [current[k] for k in current if k not in _open]
    fixed = [_open[k] for k in _open if k not in current]
    _open.clear()
    _open.update(current)
    parts = []
    if new:
        parts.append("Telegram-Stremio needs attention:\n" + "\n".join(f"- {m}" for m in new))
    if fixed:
        parts.append("Fixed:\n" + "\n".join(f"- {m}" for m in fixed))
    return "\n\n".join(parts)


async def check_once(send) -> None:
    report = await health.run_health_checks()
    text = changes(problems(report, server_load.snapshot()["facts"]))
    if text:
        await send(text)


async def watch() -> None:
    if not Telegram.OWNER_ID:
        return
    from Backend.pyrofork.bot import StreamBot

    async def send(text):
        await StreamBot.send_message(Telegram.OWNER_ID, text)

    await asyncio.sleep(120)      # let every bot and the Userbot connect after a restart
    while True:
        try:
            await check_once(send)
        except Exception as e:
            LOGGER.warning(f"[Alerts] Check failed: {e}")
        await asyncio.sleep(CHECK_EVERY)
