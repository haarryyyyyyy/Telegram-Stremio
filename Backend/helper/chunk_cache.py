"""Disk cache for the first and last MBs of streamed files.

Players read a file's start (headers, first frames) and end (MKV cues / MP4 index) on every open and
seek. Keeping those 1 MB chunks on disk makes replays and seeks start without a Telegram round trip.
It uses disk, not RAM, so it fits the 1 GB host; CHUNK_CACHE_MB caps it (0 turns it off).
"""
import asyncio
import os
import re
from pathlib import Path

MB = 1024 * 1024
HEAD_BYTES = 4 * MB
TAIL_BYTES = 4 * MB
LIMIT_BYTES = int(os.getenv("CHUNK_CACHE_MB", "1024")) * MB
CACHE_DIR = Path(os.getenv("CHUNK_CACHE_DIR", "cache/chunks"))
TRIM_EVERY = 50          # writes between size checks

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")   # Telegram unique ids are base64url
_puts = 0
stats = {"hits": 0, "misses": 0}   # since boot, shown on the Admin page's Server load panel


def wanted(offset: int, limit: int, file_size: int) -> bool:
    if LIMIT_BYTES <= 0 or file_size <= 0:
        return False
    return offset < HEAD_BYTES or offset + limit > file_size - TAIL_BYTES


def _path(uid: str, offset: int, limit: int):
    return CACHE_DIR / f"{uid}_{offset}_{limit}.bin" if _SAFE_ID.match(uid or "") else None


def _read(path) -> bytes | None:
    try:
        data = path.read_bytes()
        os.utime(path)              # mark as recently used
        return data
    except OSError:
        return None


def _write(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def trim() -> None:
    """Delete the least recently used chunks until the cache is under its limit."""
    try:
        files = [(p.stat(), p) for p in CACHE_DIR.glob("*.bin")]
    except OSError:
        return
    total = sum(st.st_size for st, _ in files)
    for st, p in sorted(files, key=lambda f: f[0].st_mtime):
        if total <= LIMIT_BYTES:
            break
        try:
            p.unlink()
            total -= st.st_size
        except OSError:
            pass


def has(uid: str, offset: int, limit: int) -> bool:
    path = _path(uid, offset, limit)
    return path is not None and path.exists()


async def get(uid: str, offset: int, limit: int) -> bytes | None:
    path = _path(uid, offset, limit)
    if path is None or not path.exists():
        return None
    return await asyncio.to_thread(_read, path)


async def put(uid: str, offset: int, limit: int, data: bytes) -> None:
    global _puts
    path = _path(uid, offset, limit)
    if path is None or not data:
        return
    try:
        await asyncio.to_thread(_write, path, data)
    except OSError:
        return
    _puts += 1
    if _puts % TRIM_EVERY == 0:
        await asyncio.to_thread(trim)
