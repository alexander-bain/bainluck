"""The last stored reading a feed card falls back to when the blend has none.

── WHAT THE FALLBACK IS FOR ─────────────────────────────────────────────────────

``routes/feed.py`` serves a card's ``current_odds`` from
``compute_aggregate_probability``. When that returns None, the feed reads the
newest non-NULL ``win_prob_snapshots`` row for the event instead, which is how
pregame Kalshi/Polymarket readings that exist only in history still reach a
card. That stays as it is.

── WHY A WITHDRAWAL HAS TO STOP IT (#11254) ─────────────────────────────────────

Live's withdrawal path (#10090) removes a venue from
``Event.win_probability_sources`` once its quote is gone. In the same commit it
writes one history row for that venue: ``home_win_probability`` NULL, and
``game_state`` ``{"live_source_withdrawal": true}``. If that venue was the only
contributor, the blend goes to None, and an "ignore NULL rows" fallback skips
the marker and lands on the venue's previous reading. The card then shows the
retired number (0.82 in the attempt86 lab) as the current probability, on the
same page where the event detail has already dropped it.

So an explicit withdrawal row for source S retires S's own rows captured at or
before it. It does NOT retire:

* other sources' readings. Their last value is still theirs, and the old
  fallback served them.
* a later reading from S. A venue that quotes again is back.
* an ordinary NULL row, or a ``live_source_withdrawal`` that is missing, false
  or the STRING ``"true"``. Live's history reader accepts only JSON ``true``, so
  this one does too. A NULL alone has never meant "withdrawn" and must not
  start meaning it here.

── WHY IT READS IN TWO PASSES (#1459) ───────────────────────────────────────────

The statement keeps the newest valid row per event by reading EVERY history
row for each id, and production has no ``(event_id, captured_at)`` index. On a
cold dyno that full-history scan was 13.9 s of the events stage after release
v5793. ``read_snapshot_fallbacks`` first runs the same statement over the last
``SNAPSHOT_FALLBACK_RECENT_WINDOW`` only, then runs the unchanged statement for
the ids that pass left unanswered. The answer is the same:

* an event with a valid reading inside the window has its newest valid reading
  inside the window, because every in-window row is newer than every row
  before it;
* whether an in-window row is retired is decided the same way in both passes.
  Only a withdrawal captured at or after the row can retire it, and such a
  withdrawal is in the window too. A source whose latest withdrawal is before
  the window retires none of its in-window rows under either statement;
* an event with no valid in-window reading gets exactly the old statement.

Rows tied on ``captured_at`` were unordered before and are unordered now; the
two passes do not change which rows tie.

Postgres only: ``DISTINCT ON`` and the JSONB operator. The real-server gate is
``tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py``.
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

WITHDRAWAL_MARKER_KEY = "live_source_withdrawal"

#: #1459: how far back pass 1 reads. Correctness does not depend on it (any
#: window gives the same answer); it decides how many ids pass 1 answers.
SNAPSHOT_FALLBACK_RECENT_WINDOW = timedelta(hours=3)

SNAPSHOT_FALLBACK_SQL = f"""
    WITH retired AS (
        SELECT event_id, source, max(captured_at) AS withdrawn_at
        FROM win_prob_snapshots
        WHERE event_id = ANY(:ids)
          AND home_win_probability IS NULL
          AND game_state -> '{WITHDRAWAL_MARKER_KEY}' = CAST('true' AS jsonb)
        GROUP BY event_id, source
    )
    SELECT DISTINCT ON (s.event_id) s.event_id, s.home_win_probability
    FROM win_prob_snapshots s
    LEFT JOIN retired r
      ON r.event_id = s.event_id AND r.source = s.source
    WHERE s.event_id = ANY(:ids)
      AND s.home_win_probability IS NOT NULL
      AND (r.withdrawn_at IS NULL OR s.captured_at > r.withdrawn_at)
    ORDER BY s.event_id, s.captured_at DESC
"""

#: #1459 pass 1: ``SNAPSHOT_FALLBACK_SQL`` with both reads bounded below by
#: ``:since``. The withdrawal CTE is bounded too: a withdrawal before the window
#: retires no in-window row, so leaving it out changes nothing but the cost.
SNAPSHOT_FALLBACK_RECENT_SQL = f"""
    WITH retired AS (
        SELECT event_id, source, max(captured_at) AS withdrawn_at
        FROM win_prob_snapshots
        WHERE event_id = ANY(:ids)
          AND captured_at >= :since
          AND home_win_probability IS NULL
          AND game_state -> '{WITHDRAWAL_MARKER_KEY}' = CAST('true' AS jsonb)
        GROUP BY event_id, source
    )
    SELECT DISTINCT ON (s.event_id) s.event_id, s.home_win_probability
    FROM win_prob_snapshots s
    LEFT JOIN retired r
      ON r.event_id = s.event_id AND r.source = s.source
    WHERE s.event_id = ANY(:ids)
      AND s.captured_at >= :since
      AND s.home_win_probability IS NOT NULL
      AND (r.withdrawn_at IS NULL OR s.captured_at > r.withdrawn_at)
    ORDER BY s.event_id, s.captured_at DESC
"""


#: #13573 Pass-2 withdrawal invalidator: bounded to Pass-1's window ``[since, now]``.
#: A cached positive Pass-2 result computed at ``checked_at`` in ``[since, now]``
#: stays exact iff no valid reading (checked by Pass 1) and no withdrawal
#: marker (checked here) arrived for that event since ``since``.
SNAPSHOT_FALLBACK_RECENT_WITHDRAWALS_SQL = f"""
    SELECT DISTINCT event_id
    FROM win_prob_snapshots
    WHERE event_id = ANY(:ids)
      AND captured_at >= :withdrawals_since
      AND home_win_probability IS NULL
      AND game_state -> '{WITHDRAWAL_MARKER_KEY}' = CAST('true' AS jsonb)
"""


# ── #11931 / #13573: Per-event Pass-2 cache (empty + positive, zero staleness) ──
#
# Pass 1 (`SNAPSHOT_FALLBACK_RECENT_SQL`) ALWAYS runs fresh over `[now - 3h, now]`.
# If Pass 1 returns no valid row for an event and Pass 2 (`SNAPSHOT_FALLBACK_SQL`,
# full history) returned `val` (either `None` when empty or a historical price)
# at `checked_at`, then at any later `now` where `now - 3h <= checked_at <= now`:
#   * Pass 1 covers `[now - 3h, now]` fresh (catching any newly arrived reading);
#   * Pass 2 at `checked_at` already resolved `(-inf, checked_at]`;
#   * if `val is None` (empty), a later withdrawal cannot create a reading;
#   * if `val is not None` (positive), a withdrawal in `[now - 3h, now]` could
#     retire `val`'s source, so cached positive hits run ONE bounded index check
#     (`SNAPSHOT_FALLBACK_RECENT_WITHDRAWALS_SQL`) over `[now - 3h, now]` and
#     re-run Pass 2 for any event with a recent withdrawal;
#   * because `now - 3h <= checked_at`, `[(-inf, checked_at]` and `[now - 3h, now]`
#     overlap with zero gap.
#
# So skipping Pass 2 for cached events returns the exact same answer while
# avoiding repeated unbounded full-history scans of `win_prob_snapshots`.

SNAPSHOT_FALLBACK_EMPTY_CACHE_ENV = "SNAPSHOT_FALLBACK_EMPTY_CACHE_ENABLED"
SNAPSHOT_FALLBACK_EMPTY_CACHE_SHARED_ENV = "SNAPSHOT_FALLBACK_EMPTY_CACHE_SHARED_ENABLED"
SNAPSHOT_FALLBACK_EMPTY_CACHE_TTL_SECONDS = 600
_EMPTY_L1_MAX_ENTRIES = 4096
_EMPTY_L2_PREFIX = "snap_fb_pass2:v2"
_EMPTY_SQL_DIGEST = hashlib.sha256(
    (
        SNAPSHOT_FALLBACK_SQL
        + SNAPSHOT_FALLBACK_RECENT_SQL
        + SNAPSHOT_FALLBACK_RECENT_WITHDRAWALS_SQL
    ).encode()
).hexdigest()[:12]

_empty_l1_lock = threading.Lock()
# Maps event_id -> (expires_at_mono, checked_at_ts, cached_prob_or_none)
_empty_l1_cache: OrderedDict[int, tuple[float, float, Any]] = OrderedDict()


def clear_snapshot_fallback_empty_cache() -> None:
    """Clear the process-local Pass-2 cache (tests)."""
    with _empty_l1_lock:
        _empty_l1_cache.clear()


def snapshot_fallback_empty_cache_enabled() -> bool:
    """Rollback switch for Pass-2 per-event caching. Defaults ON."""
    raw = os.environ.get(SNAPSHOT_FALLBACK_EMPTY_CACHE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def snapshot_fallback_empty_cache_shared_enabled() -> bool:
    """Rollback switch for the Redis L2 tier. Defaults ON."""
    raw = os.environ.get(SNAPSHOT_FALLBACK_EMPTY_CACHE_SHARED_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _empty_l1_get(event_id: int) -> tuple[float, Any] | None:
    now_mono = time.monotonic()
    with _empty_l1_lock:
        entry = _empty_l1_cache.get(event_id)
        if entry is None:
            return None
        expires_at, checked_at, value = entry
        if now_mono >= expires_at:
            _empty_l1_cache.pop(event_id, None)
            return None
        _empty_l1_cache.move_to_end(event_id)
        return checked_at, value


def _empty_l1_put(event_id: int, checked_at: float, value: Any = None) -> None:
    expires_at = time.monotonic() + SNAPSHOT_FALLBACK_EMPTY_CACHE_TTL_SECONDS
    with _empty_l1_lock:
        _empty_l1_cache[event_id] = (expires_at, checked_at, value)
        _empty_l1_cache.move_to_end(event_id)
        while len(_empty_l1_cache) > _EMPTY_L1_MAX_ENTRIES:
            _empty_l1_cache.popitem(last=False)


def _empty_l2_redis_key(event_id: int) -> str:
    return f"{_EMPTY_L2_PREFIX}:{_EMPTY_SQL_DIGEST}:{event_id}"


def _empty_l2_redis_client():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=0.5, fast_fail=True)


def _encode_l2_payload(checked_at: float, value: Any) -> str | None:
    if not math.isfinite(checked_at):
        return None
    if value is None:
        return json.dumps({"c": checked_at})
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(as_float):
        return None
    val_type = "d" if isinstance(value, Decimal) else "f"
    return json.dumps({"c": checked_at, "t": val_type, "v": str(value)})


def _decode_l2_payload(blob: Any) -> tuple[float, Any] | None:
    if not blob:
        return None
    try:
        raw = blob.decode("utf-8") if isinstance(blob, (bytes, bytearray)) else str(blob)
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return None
        checked_at = float(obj["c"])
        if not math.isfinite(checked_at):
            return None
        if "v" not in obj:
            return checked_at, None
        val_type = obj.get("t", "f")
        if val_type == "d":
            val: Any = Decimal(obj["v"])
            if not math.isfinite(float(val)):
                return None
        else:
            val = float(obj["v"])
            if not math.isfinite(val):
                return None
        return checked_at, val
    except Exception:
        logger.debug("feed_snapshot_fallback L2 decode skipped", exc_info=True)
        return None


async def _empty_l2_mget(event_ids: list[int]) -> dict[int, tuple[float, Any]]:
    if not event_ids or not snapshot_fallback_empty_cache_shared_enabled():
        return {}
    try:
        client = _empty_l2_redis_client()
        if client is None:
            return {}
        redis_keys = [_empty_l2_redis_key(eid) for eid in event_ids]
        blobs = await asyncio.to_thread(client.mget, redis_keys)
    except Exception:
        logger.debug("feed_snapshot_fallback L2 mget skipped", exc_info=True)
        return {}

    hits: dict[int, tuple[float, Any]] = {}
    for eid, blob in zip(event_ids, blobs or []):
        decoded = _decode_l2_payload(blob)
        if decoded is not None:
            hits[eid] = decoded
    return hits


async def _empty_l2_mset(entries: dict[int, Any], checked_at: float) -> None:
    if not entries or not snapshot_fallback_empty_cache_shared_enabled():
        return
    try:
        client = _empty_l2_redis_client()
        if client is None:
            return
        serialized: list[tuple[int, str]] = []
        for eid, val in entries.items():
            payload = _encode_l2_payload(checked_at, val)
            if payload is not None:
                serialized.append((eid, payload))
        if not serialized:
            return

        def _write() -> None:
            pipe = client.pipeline(transaction=False)
            for eid, payload in serialized:
                pipe.set(
                    _empty_l2_redis_key(eid),
                    payload,
                    ex=SNAPSHOT_FALLBACK_EMPTY_CACHE_TTL_SECONDS,
                )
            pipe.execute()

        await asyncio.to_thread(_write)
    except Exception:
        logger.debug("feed_snapshot_fallback L2 mset skipped", exc_info=True)


async def _lookup_cached_pass2(
    rest: list[int], *, since_ts: float, now_ts: float
) -> tuple[dict[int, Any], list[int]]:
    """Split ``rest`` into cached hits ``{event_id: value_or_none}`` and misses."""
    cached: dict[int, Any] = {}
    uncached: list[int] = []
    l2_candidates: list[int] = []
    for eid in rest:
        entry = _empty_l1_get(eid)
        if entry is not None and since_ts <= entry[0] <= now_ts:
            cached[eid] = entry[1]
            continue
        l2_candidates.append(eid)

    if l2_candidates:
        l2_hits = await _empty_l2_mget(l2_candidates)
        for eid in l2_candidates:
            entry = l2_hits.get(eid)
            if entry is not None and since_ts <= entry[0] <= now_ts:
                _empty_l1_put(eid, entry[0], entry[1])
                cached[eid] = entry[1]
            else:
                uncached.append(eid)
    return cached, uncached


async def read_snapshot_fallbacks(
    db: Any, ids: Sequence[int], *, now: datetime
) -> dict[int, Any]:
    """``{event_id: home_win_probability}``, the same answer as one
    ``SNAPSHOT_FALLBACK_SQL`` over ``ids``, read in two passes (#1459).

    ``now`` is the request's clock; pass 1 reads from ``now`` minus
    ``SNAPSHOT_FALLBACK_RECENT_WINDOW``. Both passes run on ``db`` in order and
    nothing is caught: a cancelled or failed pass raises to the caller exactly
    as the single statement did, and no partial answer is returned.
    """
    from sqlalchemy import text

    if not ids:
        return {}
    now_utc = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    since = now_utc - SNAPSHOT_FALLBACK_RECENT_WINDOW
    answered: dict[int, Any] = {}
    recent = await db.execute(
        text(SNAPSHOT_FALLBACK_RECENT_SQL), {"ids": list(ids), "since": since}
    )
    for row in recent.all():
        answered[row.event_id] = row.home_win_probability
    rest = [event_id for event_id in ids if event_id not in answered]
    if rest:
        use_cache = (
            isinstance(db, AsyncSession) and snapshot_fallback_empty_cache_enabled()
        )
        since_ts = since.timestamp()
        now_ts = now_utc.timestamp()
        if use_cache:
            cached_hits, query_rest = await _lookup_cached_pass2(
                rest, since_ts=since_ts, now_ts=now_ts
            )
            positive_cached = [eid for eid, val in cached_hits.items() if val is not None]
            if positive_cached:
                withdrawn_res = await db.execute(
                    text(SNAPSHOT_FALLBACK_RECENT_WITHDRAWALS_SQL),
                    {"ids": positive_cached, "withdrawals_since": since},
                )
                withdrawn_ids = {int(r.event_id) for r in withdrawn_res.all()}
            else:
                withdrawn_ids = set()
            for eid, val in cached_hits.items():
                if val is None:
                    continue
                if eid in withdrawn_ids:
                    query_rest.append(eid)
                else:
                    answered[eid] = val
        else:
            query_rest = rest
        if query_rest:
            older = await db.execute(text(SNAPSHOT_FALLBACK_SQL), {"ids": query_rest})
            for row in older.all():
                answered[row.event_id] = row.home_win_probability
            if use_cache:
                to_cache = {eid: answered.get(eid) for eid in query_rest}
                for eid, val in to_cache.items():
                    _empty_l1_put(eid, now_ts, val)
                await _empty_l2_mset(to_cache, now_ts)
    return answered


# ── #1480: ONE ANSWER FOR EVERY READER OF THE SAME CANDIDATE SET ─────────────
#
# The answer depends only on ``ids``: the recent window changes which pass
# answers an id, never the answer (see "WHY IT READS IN TWO PASSES"). So
# `/api/feed` reuses one answer per id set through `principal_independent_cache`
# instead of each Sports/Discover miss re-reading it, and the key has no clock.

#: The shared-artifact namespace the answer is reused under.
SNAPSHOT_FALLBACK_SHARED_NAMESPACE = "event_snapshot_fallback"


def snapshot_fallback_share_key(ids: Sequence[int]) -> tuple:
    """The shared-cache key for one fallback id set.

    The two statements' digest rotates the key if either changes; ``"v1"`` is
    the answer's shape.
    """
    from app.utils.principal_independent_cache import digest_of

    return (
        "v1",
        digest_of([SNAPSHOT_FALLBACK_SQL, SNAPSHOT_FALLBACK_RECENT_SQL]),
        digest_of(str(event_id) for event_id in ids),
    )


async def read_snapshot_fallback_artifact(
    db: Any, ids: Sequence[int], *, now: datetime
) -> dict[int, float]:
    """`read_snapshot_fallbacks` as plain floats, the form that is shared.

    The caller rounds ``float(home)`` either way, so a float here gives the
    card the same number a ``Decimal`` would. Nothing is caught.
    """
    return {
        event_id: float(home)
        for event_id, home in (
            await read_snapshot_fallbacks(db, ids, now=now)
        ).items()
    }
