"""Durable per-event trail of blend-source prunes (#9051).

The matcher drops a kalshi/polymarket key from ``Event.win_probability_sources``
when no linked market of that source remains. #9051 logs each prune, but the
heavy app has no log drain: a line lives ~3 minutes in Heroku's buffer, so a
held-page frame that shows a source missing 20 minutes later cannot be paired
with the prune that caused it.

This trail keeps the attribution where the reader can still find it:
``bainluck:blend_prune_trail:{event_id}`` holds a JSON list (oldest first) of
``{"at", "source", "phase", "committed"}``, capped and expiring after 72h.
Read it with ``GET /api/admin/redis-read?key=bainluck:blend_prune_trail:<id>``.

``committed`` is the honest half. ``phase="cleanup"`` records are written only
after that helper's own commit, so they say True. ``phase="unlink"`` records are
written where the UPDATE is staged; the caller commits later and may roll back,
so they say False and prove nothing about removal on their own.

Atomic: the append, cap and expiry run server-side in ONE Lua script per chunk,
so two writers can never both read the same list and drop each other's record
(a client-side GET then SETEX did exactly that). The stored value stays a JSON
string, so the existing GET reader is unchanged.

Bounded and best-effort: the matcher is async, so the write runs in a thread
behind a wall budget on a short-timeout fast-fail client; the first failure
stops the batch and suspends the trail for ``TRAIL_SUSPEND_S`` so an outage
costs one bounded attempt, not one per prune. A Redis failure never changes the
prune, its SQL or its commit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TRAIL_KEY_PREFIX = "bainluck:blend_prune_trail:"
TRAIL_MAX = 50
TRAIL_TTL_S = 72 * 3600
TRAIL_OP_TIMEOUT_S = 1.0  # per Redis op; an existing pool signature (#1197 budget)
TRAIL_BATCH_BUDGET_S = 2.0  # wall budget for one batch of writes
TRAIL_DEADLINE_BUDGET_S = 0.5  # the cleanup's own deadline branch gets less
TRAIL_CHUNK = 100  # records per EVAL
TRAIL_SUSPEND_S = 60.0  # after a failure, skip writes this long

# KEYS = trail keys; ARGV[1] = cap, ARGV[2] = ttl, ARGV[2+i] = record for KEYS[i].
# A stored value that is not a JSON array is replaced, never allowed to block.
_APPEND_LUA = """
local cap = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
for i, key in ipairs(KEYS) do
  local trail = {}
  local raw = redis.call('GET', key)
  if raw then
    local ok, decoded = pcall(cjson.decode, raw)
    if ok and type(decoded) == 'table' and (#decoded > 0 or next(decoded) == nil) then
      trail = decoded
    end
  end
  table.insert(trail, cjson.decode(ARGV[i + 2]))
  while #trail > cap do
    table.remove(trail, 1)
  end
  redis.call('SET', key, cjson.encode(trail), 'EX', ttl)
end
return #KEYS
"""

_suspended_until = 0.0


def trail_key(event_id: int) -> str:
    return f"{TRAIL_KEY_PREFIX}{int(event_id)}"


def _client():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(
        socket_timeout=TRAIL_OP_TIMEOUT_S,
        socket_connect_timeout=TRAIL_OP_TIMEOUT_S,
        fast_fail=True,
    )


def write_trail_batch(
    records: list, client=None, budget_s: float = TRAIL_BATCH_BUDGET_S, clock=time.monotonic
) -> int:
    """Append ``(event_id, record)`` pairs atomically. Returns records written.

    Sync; stops at the first failure or once ``budget_s`` is spent, so a slow or
    absent Redis cannot be walked through the whole list. Never raises.
    """
    global _suspended_until
    if not records:
        return 0
    start = clock()
    if start < _suspended_until:
        return 0
    deadline = start + budget_s
    written = 0
    try:
        for i in range(0, len(records), TRAIL_CHUNK):
            if clock() >= deadline:
                break
            if client is None:
                client = _client()
            chunk = records[i : i + TRAIL_CHUNK]
            client.eval(
                _APPEND_LUA,
                len(chunk),
                *[trail_key(eid) for eid, _ in chunk],
                TRAIL_MAX,
                TRAIL_TTL_S,
                *[json.dumps(rec) for _, rec in chunk],
            )
            written += len(chunk)
    except Exception as exc:
        _suspended_until = clock() + TRAIL_SUSPEND_S
        _warn("write failed, suspended %ss: %s", TRAIL_SUSPEND_S, exc)
    if written < len(records):
        _warn("dropped %s of %s records", len(records) - written, len(records))
    return written


async def record_blend_prunes(
    pairs: list, phase: str, committed: bool, budget_s: float = TRAIL_BATCH_BUDGET_S
) -> int:
    """Append ``(event_id, source)`` prunes without blocking the event loop.

    Returns records written; never raises (cancellation still propagates).
    """
    if not pairs:
        return 0
    try:
        at = datetime.now(timezone.utc).isoformat()
        records = [
            (eid, {"at": at, "source": source, "phase": phase, "committed": bool(committed)})
            for eid, source in pairs
        ]
        return await asyncio.wait_for(
            asyncio.to_thread(write_trail_batch, records, budget_s=budget_s),
            timeout=budget_s + 2 * TRAIL_OP_TIMEOUT_S,
        )
    except Exception as exc:
        _warn("batch abandoned: %r", exc)
        return 0


def _warn(msg: str, *args) -> None:
    try:
        logger.warning("blend prune trail: " + msg, *args)
    except Exception:
        pass
