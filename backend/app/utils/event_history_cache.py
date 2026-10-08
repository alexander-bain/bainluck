"""Event chart history response cache — Alex's Oct 8 load-speed push (#10090, #1469).

`GET /api/events/{id}/history` is on the event page's boot path and had NO
server cache: every open rebuilt the chart from the snapshot tables. Production
slow log, 2026-10-08: db 4–11 s per request with one query up to 9.5 s, and a
finished MLB game (15325635) re-paid 1.5–3.6 s on every open.

This keeps the SERIALIZED response per (requested id, hours, range) in process
memory and lets one build per key run at a time, so the second reader of a game
on a worker is answered from memory and a crowd arriving together shares one
build.

🔴 PROCESS MEMORY ONLY, NEVER REDIS. Production Redis is 50 MB allkeys-lru
(`middleware/latency.py`): a 400 KB chart body per event would evict cold keys
regardless of TTL — quota state and sentinel verdicts among them. Bytes, not
dicts, so the bound below is a real bound on memory.

Lease, read off the served payload's own `status` / `completed_at`:

  live                       10 s   the page re-reads every 32 s; stream frames
                                    carry the edge in between
  settled ≥ 10 min ago      600 s   the route already tells browsers an hour
  settled < 10 min ago       30 s   a settlement that just happened may reverse
  anything else              60 s

`fresh=true` never reads the cache; its result is published for the next reader.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

LIVE_TTL = 10.0
SETTLED_TTL = 600.0
FRESHLY_SETTLED_TTL = 30.0
FRESHLY_SETTLED_WINDOW = 600.0
DEFAULT_TTL = 60.0

SETTLED_STATUSES = frozenset({"completed", "closed"})

#: Per-process ceiling on cached body bytes. Oldest entries go first.
MAX_BYTES = 32 * 1024 * 1024
#: A body larger than this is never cached (it would evict everything else).
MAX_ENTRY_BYTES = 4 * 1024 * 1024

# key → (stored_at, ttl, body, cache_control)
_entries: "OrderedDict[tuple, tuple[float, float, bytes, Optional[str]]]" = OrderedDict()
_total_bytes = 0


def cache_key(event_id: int, hours: int, chart_range: str) -> tuple:
    return (int(event_id), int(hours), str(chart_range))


def _parse_iso(raw) -> Optional[datetime]:
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def lease_for(payload: dict, now: float) -> float:
    """How long this payload may be served from memory."""
    status = str(payload.get("status") or "").lower()
    if status == "live":
        return LIVE_TTL
    if status in SETTLED_STATUSES:
        completed = _parse_iso(payload.get("completed_at"))
        # No usable finish time ⇒ the short lease: a missing stamp is not
        # evidence the settlement has stopped moving.
        if completed is None or now - completed.timestamp() < FRESHLY_SETTLED_WINDOW:
            return FRESHLY_SETTLED_TTL
        return SETTLED_TTL
    return DEFAULT_TTL


def read(key: tuple, now: Optional[float] = None) -> Optional[tuple[bytes, Optional[str]]]:
    """``(body, cache_control)`` if a live entry exists, else ``None``."""
    entry = _entries.get(key)
    if entry is None:
        return None
    stored_at, ttl, body, cache_control = entry
    if (now if now is not None else time.time()) - stored_at >= ttl:
        _drop(key)
        return None
    return body, cache_control


def write(
    key: tuple,
    body: bytes,
    cache_control: Optional[str],
    ttl: float,
    now: Optional[float] = None,
) -> None:
    global _total_bytes
    if ttl <= 0 or len(body) > MAX_ENTRY_BYTES:
        return
    _drop(key)
    _entries[key] = (now if now is not None else time.time(), ttl, body, cache_control)
    _total_bytes += len(body)
    while _total_bytes > MAX_BYTES and _entries:
        _drop(next(iter(_entries)))


def _drop(key: tuple) -> None:
    global _total_bytes
    entry = _entries.pop(key, None)
    if entry is not None:
        _total_bytes -= len(entry[2])


def total_bytes() -> int:
    return _total_bytes


def _reset_for_tests() -> None:
    global _total_bytes
    _entries.clear()
    _total_bytes = 0
