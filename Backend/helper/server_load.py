"""Live server load for the Admin page: CPU, memory, network, disk, event-loop lag and streams.

A background task samples every SAMPLE_EVERY seconds and keeps the last 10 minutes. It reads /proc on Linux
(the server); on other systems the /proc values are None and the page shows a dash.
"""
import asyncio
import os
import shutil
import time
from collections import deque

from Backend.logger import LOGGER

SAMPLE_EVERY = 5
history: deque = deque(maxlen=120)          # 120 x 5 s = 10 minutes
_prev: dict = {}
_static: dict = {}


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def cpu_times(stat: str = None):
    """(busy, total) jiffies of the whole machine from /proc/stat."""
    first = (stat if stat is not None else _read("/proc/stat")).split("\n", 1)[0].split()
    if len(first) < 8 or first[0] != "cpu":
        return None
    values = [int(v) for v in first[1:8]]
    idle = values[3] + values[4]               # idle + iowait
    total = sum(values)
    return total - idle, total


def meminfo(text: str = None) -> dict:
    out = {}
    for line in (text if text is not None else _read("/proc/meminfo")).splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[key] = int(parts[0]) * 1024
    return out


def net_bytes(text: str = None):
    """(received, sent) bytes over every interface except loopback, from /proc/net/dev."""
    rx = tx = 0
    found = False
    for line in (text if text is not None else _read("/proc/net/dev")).splitlines()[2:]:
        name, _, data = line.partition(":")
        fields = data.split()
        if name.strip() == "lo" or len(fields) < 9:
            continue
        rx += int(fields[0])
        tx += int(fields[8])
        found = True
    return (rx, tx) if found else None


def _rss() -> int | None:
    for line in _read("/proc/self/status").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def _dir_size(path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
    except OSError:
        pass
    return total


def _rate(now, key, value):
    """Per-second change of a counter since the previous sample."""
    old = _prev.get(key)
    _prev[key] = (now, value)
    if old is None or value is None or old[1] is None or now <= old[0]:
        return None
    return max(0.0, (value - old[1]) / (now - old[0]))


def sample(lag_ms: float = 0.0) -> dict:
    from Backend.helper.custom_dl import ACTIVE_STREAMS
    from Backend.pyrofork.bot import work_loads

    now = time.monotonic()
    cpu = cpu_times()
    cpu_pct = None
    old_cpu = _prev.get("cpu")
    _prev["cpu"] = cpu
    if cpu and old_cpu and cpu[1] > old_cpu[1]:
        cpu_pct = 100.0 * (cpu[0] - old_cpu[0]) / (cpu[1] - old_cpu[1])

    times = os.times()
    app_cpu = _rate(now, "app_cpu", times.user + times.system)
    net = net_bytes()
    mem = meminfo()
    total, avail = mem.get("MemTotal"), mem.get("MemAvailable")

    point = {
        "t": time.time(),
        "cpu": round(cpu_pct, 1) if cpu_pct is not None else None,
        "app_cpu": round(100.0 * app_cpu / (os.cpu_count() or 1), 1) if app_cpu is not None else None,
        "mem": round(100.0 * (total - avail) / total, 1) if total and avail is not None else None,
        "rss": _rss(),
        "rx": _rate(now, "rx", net[0] if net else None),
        "tx": _rate(now, "tx", net[1] if net else None),
        "lag": round(lag_ms, 1),
        "streams": sum(1 for s in ACTIVE_STREAMS.values() if s.get("status") == "active"),
        "bot_load": sum(max(0, v) for v in work_loads.values()),
    }
    history.append(point)
    return point


def _slow_facts() -> dict:
    """Disk, swap and cache size change slowly: refresh them once a minute, not every sample."""
    if time.monotonic() - _static.get("at", -1e9) < 60:
        return _static
    from Backend.helper.chunk_cache import CACHE_DIR, LIMIT_BYTES
    mem = meminfo()
    try:
        disk = shutil.disk_usage(".")
        disk_total, disk_free = disk.total, disk.free
    except OSError:
        disk_total = disk_free = None
    _static.update(
        at=time.monotonic(),
        mem_total=mem.get("MemTotal"),
        swap_total=mem.get("SwapTotal"),
        swap_used=(mem["SwapTotal"] - mem.get("SwapFree", 0)) if mem.get("SwapTotal") else None,
        disk_total=disk_total, disk_free=disk_free,
        cache_bytes=_dir_size(CACHE_DIR), cache_limit=LIMIT_BYTES,
        load_avg=list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        cpu_count=os.cpu_count(),
    )
    return _static


def snapshot() -> dict:
    facts = {k: v for k, v in _slow_facts().items() if k != "at"}
    return {"every": SAMPLE_EVERY, "now": history[-1] if history else None, "facts": facts, "history": list(history)}


async def sampler() -> None:
    loop = asyncio.get_running_loop()
    sample()
    while True:
        start = loop.time()
        await asyncio.sleep(SAMPLE_EVERY)
        lag = max(0.0, (loop.time() - start - SAMPLE_EVERY) * 1000)   # how late the loop woke us: a busy server wakes late
        try:
            sample(lag)
        except Exception as e:
            LOGGER.warning(f"[Load] Sample failed: {e}")
