import asyncio
import time
from datetime import datetime

import httpx

import Backend.pyrofork.bot as botmod
from Backend import db
from Backend.helper.metadata import get_tmdb_client, tmdb_api_key
from Backend.helper.settings_manager import SettingsManager
from Backend.pyrofork.bot import (
    StreamBot,
    client_dc_map,
    client_failures,
    multi_clients,
    work_loads,
)

#----- Rough Atlas free-tier (M0) storage ceiling, used only as a usage guide
_FREE_TIER_BYTES = 512 * 1024 * 1024

#----- Cache TTLs (seconds) so the panel can poll often without hammering DB/TMDB.
#----- Bot clients are always computed fresh (in-memory) for realtime load.
_TTL = {"databases": 30, "tmdb": 300, "base_url": 60, "userbot": 300}
_cache: dict = {}


async def _cached(key: str, producer, force: bool = False):
    now = time.monotonic()
    entry = _cache.get(key)
    if not force and entry and (now - entry[0]) < _TTL[key]:
        return entry[1]
    result = await producer()
    _cache[key] = (now, result)
    return result


async def _check_databases() -> dict:
    items = []
    for key, mdb in db.dbs.items():
        entry = {"name": key, "status": "down", "size_mb": 0, "usage_pct": 0, "message": ""}
        try:
            await asyncio.wait_for(mdb.command("ping"), timeout=6)
            entry["status"] = "ok"
            try:
                stats = await asyncio.wait_for(mdb.command("dbstats"), timeout=6)
                size = stats.get("storageSize", 0) or 0
                entry["size_mb"] = round(size / (1024 * 1024), 1)
                entry["usage_pct"] = min(100, round(size / _FREE_TIER_BYTES * 100, 1))
            except Exception:
                pass
        except Exception as e:
            entry["message"] = str(e)[:140]
        items.append(entry)

    up = sum(1 for i in items if i["status"] == "ok")
    status = "ok" if items and up == len(items) else ("degraded" if up else "down")
    return {"key": "databases", "label": "Databases", "status": status, "up": up, "total": len(items), "items": items}


def _check_bots() -> dict:
    clients = []
    for idx in sorted(multi_clients.keys()):
        client = multi_clients[idx]
        clients.append({
            "name": f"Bot {idx + 1}",
            "connected": bool(getattr(client, "is_connected", False)),
            "dc": client_dc_map.get(idx),
            "workload": work_loads.get(idx, 0),
            "failures": client_failures.get(idx, 0),
        })
    up = sum(1 for c in clients if c["connected"])
    status = "ok" if clients and up == len(clients) else ("degraded" if up else "down")
    return {
        "key": "bots", "label": "Telegram Clients", "status": status,
        "up": up, "total": len(clients), "items": clients,
        "primary_connected": bool(getattr(StreamBot, "is_connected", False)),
    }


async def _check_tmdb() -> dict:
    if not tmdb_api_key():
        return {"key": "tmdb", "label": "TMDB API", "status": "not_configured",
                "message": "No TMDB API key set — metadata matching will be limited."}
    try:
        movie = await asyncio.wait_for(get_tmdb_client().movie(550).details(), timeout=10)
        if getattr(movie, "title", None):
            return {"key": "tmdb", "label": "TMDB API", "status": "ok", "message": "API key is valid."}
        return {"key": "tmdb", "label": "TMDB API", "status": "error", "message": "Unexpected TMDB response."}
    except Exception as e:
        return {"key": "tmdb", "label": "TMDB API", "status": "error", "message": str(e)[:140]}


async def _check_base_url() -> dict:
    base = SettingsManager.current().base_url
    if not base:
        return {"key": "base_url", "label": "Base URL", "status": "not_configured",
                "message": "Base URL not set — Stremio can't reach your streams."}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(base)
        return {"key": "base_url", "label": "Base URL", "status": "ok",
                "message": f"Reachable (HTTP {resp.status_code}).", "url": base}
    except Exception as e:
        return {"key": "base_url", "label": "Base URL", "status": "error", "message": str(e)[:140], "url": base}


def _chat_ref(channel: str):
    c = str(channel).strip().replace("-100", "", 1)
    return int(f"-100{c}") if c.isdigit() else channel


#----- The Userbot deletes what bots cannot (messages older than 48 hours): is it logged in, and may it delete in each channel
async def _check_userbot() -> dict:
    from Backend.helper.task_manager import ensure_peer
    ub = botmod.Userbot
    base = {"key": "userbot", "label": "Userbot"}
    if ub is None:
        return {**base, "status": "not_configured",
                "message": "Not logged in. Bots cannot delete messages older than 48 hours. Log in under Settings, Telegram Userbot."}
    me = getattr(ub, "me", None)
    who = f"@{me.username}" if me and me.username else (getattr(me, "first_name", "") or "the account")
    if not getattr(ub, "is_connected", False):
        return {**base, "status": "error", "message": f"Logged in as {who} but disconnected. Restart the server."}

    settings = SettingsManager.current()
    titles = settings.to_dict().get("channel_titles") or {}
    items = []
    for channel in sorted(SettingsManager._all_channel_ids(settings.to_dict())):
        name = titles.get(channel) or titles.get(str(channel).replace("-100", "", 1)) or channel
        entry = {"name": name, "can_delete": False, "message": ""}
        try:
            ref = _chat_ref(channel)
            if isinstance(ref, int) and not await ensure_peer(ub, ref):
                entry["message"] = "not a member"
            else:
                m = await asyncio.wait_for(ub.get_chat_member(ref, "me"), timeout=8)
                entry["can_delete"] = bool(getattr(getattr(m, "privileges", None), "can_delete_messages", False))
                entry["message"] = "can delete" if entry["can_delete"] else "no Delete messages right"
        except Exception as e:
            entry["message"] = str(e)[:80]
        items.append(entry)

    ok = sum(1 for i in items if i["can_delete"])
    status = "ok" if ok == len(items) else ("degraded" if ok else "error")
    return {**base, "status": status, "message": f"Logged in as {who}. Can delete in {ok} of {len(items)} channels.",
            "up": ok, "total": len(items), "items": items}


async def run_health_checks(force: bool = False) -> dict:
    databases = await _cached("databases", _check_databases, force)
    bots = _check_bots()
    tmdb = await _cached("tmdb", _check_tmdb, force)
    base_url = await _cached("base_url", _check_base_url, force)
    userbot = await _cached("userbot", _check_userbot, force)

    statuses = [databases["status"], bots["status"], tmdb["status"], base_url["status"]]
    if userbot["status"] != "not_configured":   # optional: only a logged-in Userbot that cannot delete is a problem
        statuses.append(userbot["status"])
    if "down" in (databases["status"], bots["status"]):
        overall = "critical"
    elif any(s in ("down", "degraded", "error", "not_configured") for s in statuses):
        overall = "warning"
    else:
        overall = "ok"

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "overall": overall,
        "sections": [databases, bots, tmdb, base_url, userbot],
    }
