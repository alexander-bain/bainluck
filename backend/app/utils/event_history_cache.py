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

Lease (Root scope, Oct 8): FINISHED games only, 45 s. Anything else — live,
scheduled, a past-start game nobody settled — is never stored, so no live chart
can be served older than it was before this cache existed. Never stored either:

  * a PARTIAL body — the build swallows a failed read (scores, ESPN, win-prob
    history, periods, spread, aggregate, moments, start recovery, refill) and
    returns what it has; that body stays the reader's answer but is not kept
    (`mark_partial`, called from each of those `except` blocks);
  * a chart whose refill was just ENQUEUED — it is about to change.

`fresh=true` neither reads nor writes the cache.
"""

from __future__ import annotations

import contextvars
import time
from collections import OrderedDict
from typing import Optional

FINISHED_TTL = 45.0

#: Per-process ceiling on cached body bytes. Oldest entries go first.
MAX_BYTES = 32 * 1024 * 1024
#: A body larger than this is never cached (it would evict everything else).
MAX_ENTRY_BYTES = 4 * 1024 * 1024

# key → (stored_at, ttl, body, cache_control)
_entries: "OrderedDict[tuple, tuple[float, float, bytes, Optional[str]]]" = OrderedDict()
_total_bytes = 0


def cache_key(event_id: int, hours: int, chart_range: str) -> tuple:
    return (int(event_id), int(hours), str(chart_range))


class BuildMarks:
    """What the build learned about its own body, read by the cache policy."""

    __slots__ = ("finished", "partial")

    def __init__(self) -> None:
        self.finished = False
        self.partial = False


_marks: "contextvars.ContextVar[Optional[BuildMarks]]" = contextvars.ContextVar(
    "event_history_build_marks", default=None
)


def begin_marks() -> tuple[BuildMarks, contextvars.Token]:
    """Install fresh marks for one build; pass the token to ``end_marks``."""
    marks = BuildMarks()
    return marks, _marks.set(marks)


def end_marks(token: contextvars.Token) -> None:
    _marks.reset(token)


def mark_partial() -> None:
    """The build swallowed a failed read: its body must not be stored."""
    marks = _marks.get()
    if marks is not None:
        marks.partial = True


def mark_finished(finished) -> None:
    marks = _marks.get()
    if marks is not None:
        marks.finished = bool(finished)


def lease_for(marks: BuildMarks, payload) -> float:
    """Seconds this body may be served from memory; 0 = do not store."""
    if not isinstance(payload, dict) or not marks.finished or marks.partial:
        return 0.0
    refill = payload.get("on_demand_backfill")
    if isinstance(refill, dict) and refill.get("enqueue"):
        return 0.0
    return FINISHED_TTL


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
