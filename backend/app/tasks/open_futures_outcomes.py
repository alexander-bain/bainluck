"""Maintain the names and price poll fields in ``open_futures_outcomes``.

THE SHIP. The dropdown and the Search page match outcome names over this copy
(~262 k rows) instead of ``futures_outcomes`` (8.8 M), so a first keystroke like
"chi" or "mid" stops paying for closed markets. Readers use the copy only while
this task's state is current (``app.utils.open_futures_outcomes``).

ONE PASS, every 5 minutes, each step its own short transaction:

1. **Watermark.** ``max(futures_outcomes.id)`` before anything is read.
2. **Reopened markets.** Pick open ``futures_markets`` IDs with zero rows in
   the copy first (``REOPENED_MARKET_IDS_SQL``), then batch-upsert all their
   outcomes from ``futures_outcomes`` by ``market_id = ANY(:market_ids)`` before
   the delta so newly added outcomes above ``reader_floor`` never hide older legs
   and empty/normal passes never plan a full join across ``futures_outcomes``.
3. **Delta.** Outcomes of open markets with an id above the PREVIOUS pass's
   reader floor (one pass of slack for a row whose id was taken before it
   committed), upserted. Primary-key range; a few thousand rows.
4. **Closed markets out.** Copy rows whose market is no longer ``open``.
5. **One rotating slice reconciled** (``market_id % SLICES``): the slice's open
   outcomes upserted (renames, missed edits) and its rows that no longer
   exist deleted, in one statement over one read of the slice. Twelve slices,
   so every open outcome is re-read once an hour.
6. **State** written with a TTL of ``STALE_AFTER_SECONDS``: ``watermark`` (this
   pass), ``reader_floor`` (the previous pass's watermark), ``pass_at``,
   ``cycle_complete`` and the slice cursor.

A FIRST FILL (no state, an expired state, or new copy columns) runs each
slice in the pass, budget permitting, and sets ``cycle_complete`` only once
all twelve are done. A pass that runs out of budget resumes at its cursor on
the next run.

COST, measured on production 2026-11-08 06:15 PT with read-only EXPLAIN ANALYZE:
one slice's read is ~21.9 k outcome rows in 2.4 s (1,805 blocks read); the open
markets' status scan 0.8-1.4 s; a delta over ~104 k ids of the sequence, 28 k
rows in 4.9 s cold. A steady pass is one slice, one delta and one anti-join —
about 5 s of database time every 5 minutes; the first fill is ~30 s once.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import BigInteger, bindparam, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY

from app.utils.open_futures_outcomes import OUTCOME_COPY_VERSION, STALE_AFTER_SECONDS, STATE_KEY

logger = logging.getLogger(__name__)

#: Rotation width: every open outcome is re-read once per ``SLICES`` passes.
SLICES = 12

#: A pass's wall budget, under the task's 150 s soft limit.
PASS_BUDGET_SECONDS = 110

#: Per-statement bound. A slice read measured 2.4 s; this is headroom for a
#: cold, contended database, never a working limit.
STATEMENT_TIMEOUT_MS = 60_000

#: One pass at a time across every worker.
LOCK_KEY = "bainluck:open_futures_outcomes:lock"
LOCK_SECONDS = 170

_UPSERT_TAIL = """
ON CONFLICT (outcome_id) DO UPDATE
   SET name = EXCLUDED.name, market_id = EXCLUDED.market_id,
       external_id = EXCLUDED.external_id, is_winner = EXCLUDED.is_winner,
       resolution_source = EXCLUDED.resolution_source
 WHERE (open_futures_outcomes.name, open_futures_outcomes.market_id,
        open_futures_outcomes.external_id, open_futures_outcomes.is_winner,
        open_futures_outcomes.resolution_source)
       IS DISTINCT FROM (EXCLUDED.name, EXCLUDED.market_id,
                         EXCLUDED.external_id, EXCLUDED.is_winner, EXCLUDED.resolution_source)
"""

#: Batch size when restoring outcomes of reopened markets (`market_id = ANY(...)`).
REOPENED_MARKET_BATCH_SIZE = 500

REOPENED_MARKET_IDS_SQL = text(
    """
SELECT m.id
  FROM futures_markets m
 WHERE m.status = 'open'
   AND NOT EXISTS (
       SELECT 1 FROM open_futures_outcomes t WHERE t.market_id = m.id
   )
"""
)

REOPENED_OUTCOMES_SQL = text(
    """
INSERT INTO open_futures_outcomes (outcome_id, market_id, name, external_id, is_winner, resolution_source)
SELECT o.id, o.market_id, o.name, o.external_id, o.is_winner, o.resolution_source
  FROM futures_outcomes o
  JOIN futures_markets m ON m.id = o.market_id
 WHERE o.market_id = ANY(:market_ids)
   AND m.status = 'open'
"""
    + _UPSERT_TAIL
).bindparams(bindparam("market_ids", type_=ARRAY(BigInteger)))

DELTA_SQL = text(
    """
INSERT INTO open_futures_outcomes (outcome_id, market_id, name, external_id, is_winner, resolution_source)
SELECT o.id, o.market_id, o.name, o.external_id, o.is_winner, o.resolution_source
  FROM futures_outcomes o
  JOIN futures_markets m ON m.id = o.market_id
 WHERE o.id > :floor AND m.status = 'open'
"""
    + _UPSERT_TAIL
)

CLOSED_SQL = text(
    """
DELETE FROM open_futures_outcomes t
 WHERE NOT EXISTS (
       SELECT 1 FROM futures_markets m WHERE m.id = t.market_id AND m.status = 'open')
"""
)

SLICE_SQL = text(
    """
WITH src AS (
    SELECT o.id, o.market_id, o.name, o.external_id, o.is_winner, o.resolution_source
      FROM futures_outcomes o
      JOIN futures_markets m ON m.id = o.market_id
     WHERE m.status = 'open' AND m.id % :slices = :slice
), up AS (
    INSERT INTO open_futures_outcomes (outcome_id, market_id, name, external_id, is_winner, resolution_source)
    SELECT id, market_id, name, external_id, is_winner, resolution_source FROM src
"""
    + _UPSERT_TAIL
    + """
    RETURNING 1
)
DELETE FROM open_futures_outcomes t
 WHERE t.market_id % :slices = :slice
   AND t.outcome_id NOT IN (SELECT id FROM src)
"""
)


def _load_state(rc) -> dict:
    try:
        raw = rc.get(STATE_KEY)
        state = json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001 — an unreadable state is a fresh start
        return {}
    return state if isinstance(state, dict) else {}


async def _step(session, stmt, params: dict | None = None) -> int:
    result = await session.execute(stmt, params or {})
    await session.commit()
    return int(result.rowcount or 0) if result.rowcount is not None else 0


async def _sync_reopened_markets(session) -> tuple[int, float]:
    """Pick reopened market IDs first, then upsert their outcomes in batches.

    Fable (#13865) noted that joining ``futures_markets`` directly to
    ``futures_outcomes`` lets the planner risk scanning all open outcomes when
    few markets are missing copy rows. Materializing the candidate ``market_id``
    list first ensures zero reads of ``futures_outcomes`` when empty and bounded
    index probes via ``ix_futures_outcomes_market_id`` otherwise.
    """
    t0 = time.monotonic()
    market_ids = [int(mid) for mid in (await session.scalars(REOPENED_MARKET_IDS_SQL)).all()]
    if not market_ids:
        await session.commit()
        return 0, round(time.monotonic() - t0, 3)

    restored = 0
    for start in range(0, len(market_ids), REOPENED_MARKET_BATCH_SIZE):
        batch = market_ids[start : start + REOPENED_MARKET_BATCH_SIZE]
        res = await session.execute(REOPENED_OUTCOMES_SQL, {"market_ids": batch})
        restored += int(res.rowcount or 0) if res.rowcount is not None else 0
    await session.commit()
    return restored, round(time.monotonic() - t0, 3)


async def _refresh_open_futures_outcomes(budget_seconds: int = PASS_BUDGET_SECONDS) -> dict[str, Any]:
    """One maintenance pass. Returns a summary with a ``terminal`` (task_verdict)."""
    from app.models.models import FuturesOutcome
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    rc = get_redis_client()
    if not rc.set(LOCK_KEY, "1", nx=True, ex=LOCK_SECONDS):
        return {"terminal": "partial", "skipped": "another pass holds the lock"}
    started = time.monotonic()
    deadline = started + budget_seconds
    summary: dict[str, Any] = {
        "slices": [],
        "reopened": 0,
        "reopened_seconds": 0.0,
        "delta": 0,
        "closed": 0,
    }
    try:
        state = _load_state(rc)
        same_version = state.get("version") == OUTCOME_COPY_VERSION
        filling = not same_version or not state.get("cycle_complete")
        cursor = int(state.get("slice_cursor") or 0) % SLICES if same_version else 0
        filled = int(state.get("filled_slices") or 0) if same_version else 0
        if not filling:
            filled = SLICES

        # A fresh engine per pass, disposed on exit (Fable, #12358): the task runs
        # under `asyncio.run`, a new loop each invocation, and one prefork child
        # runs many passes, so the module-level engine's pooled connections would
        # belong to a loop that has closed. The statement bound rides the
        # connection (#4482), never a `SET`.
        async with get_task_session(statement_timeout_ms=STATEMENT_TIMEOUT_MS) as session:
            watermark = int(
                (await session.execute(select(func.max(FuturesOutcome.id)))).scalar() or 0
            )
            await session.commit()

            # Slices first on a fill, so the delta and the closed-market sweep
            # then run over a table that holds everything.
            want = SLICES - filled if filling else 1
            for _ in range(want):
                if time.monotonic() >= deadline:
                    break
                n = await _step(session, SLICE_SQL, {"slices": SLICES, "slice": cursor})
                summary["slices"].append({"slice": cursor, "deleted": n})
                cursor = (cursor + 1) % SLICES
                if filling:
                    filled += 1

            # Run reopened BEFORE delta: if a reopened market also gained one
            # new outcome > previous_floor, running DELTA_SQL first would insert
            # that single row and cause NOT EXISTS to skip the market's older
            # legs. Only run on steady passes (when all slices are populated).
            if not filling and time.monotonic() < deadline:
                reopened_count, reopened_secs = await _sync_reopened_markets(session)
                summary["reopened"] = reopened_count
                summary["reopened_seconds"] = reopened_secs
            previous_floor = state.get("reader_floor")
            if isinstance(previous_floor, int) and time.monotonic() < deadline:
                summary["delta"] = await _step(session, DELTA_SQL, {"floor": previous_floor})
            if time.monotonic() < deadline:
                summary["closed"] = await _step(session, CLOSED_SQL)
            rows = int(
                (await session.execute(text("SELECT count(*) FROM open_futures_outcomes"))).scalar()
                or 0
            )
            await session.commit()

        complete = filled >= SLICES
        previous_watermark = state.get("watermark")
        new_state = {
            "version": OUTCOME_COPY_VERSION,
            "watermark": watermark,
            # Readers match ids above this on `futures_outcomes` directly: the
            # previous pass's watermark, so a row committed late is still seen.
            "reader_floor": (
                previous_watermark
                if isinstance(previous_watermark, int)
                else watermark
            ),
            "pass_at": time.time(),
            "cycle_complete": complete,
            "slice_cursor": cursor,
            "filled_slices": filled,
            "rows": rows,
        }
        rc.setex(STATE_KEY, STALE_AFTER_SECONDS, json.dumps(new_state))
        summary.update(
            rows=rows,
            watermark=watermark,
            cycle_complete=complete,
            seconds=round(time.monotonic() - started, 1),
            terminal="complete" if complete else "partial",
        )
        return summary
    except Exception:
        # A failed pass must not leave readers on a copy it could not maintain.
        try:
            rc.delete(STATE_KEY)
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        try:
            rc.delete(LOCK_KEY)
        except Exception:  # noqa: BLE001
            pass
