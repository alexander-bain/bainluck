"""The Kalshi cliff drain — fetch-now-or-never price history (#1586, queue 355).

What this is for
----------------
Kalshi keeps a settled market's price history for a measured 74–86 days and then
deletes it permanently (gotcha #35, ``app/utils/kalshi_retention.py``, measured
2026-08-07). Roughly **7,800 markets a week** cross that horizon. Measured
2026-08-14: 99,228 resolved Kalshi outcomes still sit inside the window, 15,293
of them in the at-risk 74–86 day band, and 76,644 are already past it and gone
for good.

Everything past the cliff is unrecoverable by any means. Everything inside it is
recoverable *today and not tomorrow*. That asymmetry is the entire design brief:
this rail is ordered by what expires soonest, and it is resumable so that no
run's work has to be redone.

Why a new rail rather than a bigger limit on the old one
--------------------------------------------------------
``_backfill_kalshi_price_history`` already selects oldest-first inside the
retention floor (CAL-P009 put the floor there). It cannot drain the cohort, for
three reasons that are properties of its shape rather than of its budget:

1. **It has no watermark.** Its predicate is "resolved outcomes with no
   snapshots", ordered oldest-first, ``LIMIT n``. An outcome the API has no
   history for stays in that predicate forever, so the next run re-selects the
   same head rows and re-fetches them. A cohort whose leading edge is mostly
   empty is a cohort the rail cannot page past — gotcha #41's shape one level
   down: the ordering is right and the sweep still never arrives.
2. **Its candlestick window is wrong for old markets.** The API call defaults to
   ``now-90d .. now``. For a market that settled 80 days ago, that window
   overlaps the market's life by about ten days and is otherwise empty — the
   fetch "succeeds", returns almost nothing, and the outcome is written off. The
   drain asks for the window around the market's OWN settlement instead.
3. **It cannot tell an empty answer from a dead one.** ``if not candles:
   api_empty += 1`` conflates "Kalshi purged this" with "this market genuinely
   had no trades" with "the request failed and the client swallowed it" — gotcha
   #53 exactly. Those three demand different responses and the counter that
   would tell them apart did not exist.

The addressing path
-------------------
Per-ticker, through ``KalshiAPIService`` (``https://api.elections.kalshi.com/
trade-api/v2``) — the path the retention probe validated at 200 for 61–68 day
markets. Note what this deliberately is NOT: the settled-events pagination
(``GET /events?status=settled&series_ticker=X``) is far shallower than the cliff
— KXNBAPTS reached back only 74 days — so markets near the edge are reachable
only from tickers we already hold in our own database. We hold them. That is the
whole opening.

A window's ad-hoc probe read all-404 against a different addressing path and
concluded the cohort was already purged; the control (live OPEN markets, which
404'd identically) disproved it. Hence the rule this module keeps: **a negative
result about upstream is only believable next to a positive control.**
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.models import FuturesOddsSnapshot
from app.tasks.base import get_task_session
from app.utils.kalshi_retention import (
    AT_RISK_AGE_DAYS,
    PROVABLY_PURGED_AGE_DAYS,
)

logger = logging.getLogger(__name__)

#: Redis key holding the resumable watermark + running totals.
STATE_KEY = "bainluck:kalshi:cliff_drain:state"
_STATE_TTL_S = 86400 * 30

#: Commit + checkpoint every N outcomes. Small enough that a SIGKILL costs at
#: most this many outcomes of re-work, large enough not to thrash Redis.
CHECKPOINT_EVERY = 25

#: Per-run ceiling on existence probes. Disambiguating an empty answer costs a
#: second API call, and on a run that is mostly empty that would double the
#: request count for a fact we only need a sample of. Unprobed empties are
#: reported as their own bucket — never folded into either explanation.
MAX_EXISTENCE_PROBES = 200

#: How much of a market's life to ask for, anchored on ITS settlement rather
#: than on now. Kalshi's candlestick endpoint is happy with a wide range.
LOOKBACK_DAYS = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Resumable state
# --------------------------------------------------------------------------


def _default_state() -> dict[str, Any]:
    return {
        "cursor_date": None,     # ISO resolution_date of the last outcome processed
        "cursor_id": 0,          # its outcome id — ties broken deterministically
        "outcomes_seen": 0,
        "snapshots_created": 0,
        "outcomes_with_history": 0,
        "empty_purged": 0,
        "empty_present": 0,
        "empty_unprobed": 0,
        "fetch_errors": 0,
        "runs": 0,
        "last_run_at": None,
        "started_at": None,
    }


def load_state() -> dict[str, Any]:
    """Current drain state. A Redis miss starts a fresh drain, never a crash."""
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(STATE_KEY)
        if not raw:
            return _default_state()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        state = _default_state()
        state.update(json.loads(raw))
        return state
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("cliff drain: state load failed (%s) — starting fresh", exc)
        return _default_state()


def save_state(state: dict[str, Any]) -> bool:
    """Persist the watermark. Returns whether it actually landed.

    The return value matters: a drain whose checkpoint silently fails is a drain
    that re-grinds its head every run while reporting progress. The caller
    downgrades its own terminal when this is False rather than claiming a
    resumable sweep it cannot resume.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(STATE_KEY, _STATE_TTL_S, json.dumps(state))
        return True
    except Exception as exc:
        logger.warning("cliff drain: checkpoint write FAILED: %s", exc)
        return False


def reset_state() -> dict[str, Any]:
    """Rewind the watermark to the start of the window (admin escape hatch)."""
    fresh = _default_state()
    save_state(fresh)
    return fresh


# --------------------------------------------------------------------------
# Cohort
# --------------------------------------------------------------------------

# Both bounds, per gotcha #41. The FLOOR (`>= now - purge_days`) keeps the sweep
# off the ~76K rows that are provably gone; without it, oldest-first spends the
# whole run on the already-dead and never reaches the dying. The ORDER
# (oldest-first) then means "oldest still-recoverable", which is exactly the
# at-risk band. The WATERMARK (`> cursor`) is what makes it a drain rather than
# a rescan: rows that yield nothing are still passed, permanently.
#
# Note the watermark direction is safe against cohort churn. Rows AGE IN at the
# young end (resolution_date near now), which is ahead of the watermark in ASC
# order, so they are picked up on a later run. Rows FALL OUT at the old end,
# behind the watermark, and are correctly never revisited.
_COHORT_SQL = """
    SELECT fo.id                AS outcome_id,
           fo.external_id       AS ticker,
           fm.resolution_date   AS resolution_date
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi'
      AND fm.status = 'resolved'
      AND fo.external_id IS NOT NULL
      AND fm.resolution_date IS NOT NULL
      AND fm.resolution_date >= now() - make_interval(days => :purge_days)
      AND fm.resolution_date <= now()
      AND NOT EXISTS (
          SELECT 1 FROM futures_odds_snapshots fos
          WHERE fos.outcome_id = fo.id
      )
      AND (fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)
    ORDER BY fm.resolution_date ASC, fo.id ASC
    LIMIT :limit
"""

# The same predicate, counted, bounded so it can never become the slow query
# that makes operators stop asking for progress.
_REMAINING_SQL = """
    SELECT count(*) FROM (
        SELECT 1
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.source = 'kalshi'
          AND fm.status = 'resolved'
          AND fo.external_id IS NOT NULL
          AND fm.resolution_date IS NOT NULL
          AND fm.resolution_date >= now() - make_interval(days => :purge_days)
          AND fm.resolution_date <= now()
          AND NOT EXISTS (
              SELECT 1 FROM futures_odds_snapshots fos
              WHERE fos.outcome_id = fo.id
          )
          AND (fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)
        LIMIT :cap
    ) t
"""

#: Cap on the remaining-count probe. Reported honestly as `>= cap` when hit —
#: a truncated count presented as a total is the silent-cap failure.
_REMAINING_CAP = 250_000

_EPOCH = "1970-01-01T00:00:00+00:00"


def _cursor_params(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "cursor_date": state.get("cursor_date") or _EPOCH,
        "cursor_id": int(state.get("cursor_id") or 0),
    }


# --------------------------------------------------------------------------
# The drain
# --------------------------------------------------------------------------


async def run_cliff_drain(
    limit: int = 400,
    deadline: Optional[float] = None,
    probe_empties: bool = True,
) -> dict[str, Any]:
    """Fetch price history for the oldest still-recoverable Kalshi outcomes.

    ``deadline`` is a ``time.monotonic()`` timestamp (the caller's budget). The
    loop checks it before every outcome — one outcome is the longest single
    uninterrupted operation here — so a truncated run banks its watermark and
    the next run continues rather than restarting (budget-guard-inner-op).

    The returned summary carries a ``terminal`` so ``task_verdict`` can read it:
    a run that fetched nothing must not be recorded as a healthy one.
    """
    started = time.monotonic()
    state = load_state()
    state["runs"] = int(state.get("runs") or 0) + 1
    if not state.get("started_at"):
        state["started_at"] = _now().isoformat()

    run = {
        "outcomes_seen": 0,
        "outcomes_with_history": 0,
        "snapshots_created": 0,
        "empty_purged": 0,
        "empty_present": 0,
        "empty_unprobed": 0,
        "fetch_errors": 0,
    }
    # Cumulative totals as they stood BEFORE this run — the base every
    # checkpoint adds the run deltas to, so repeated checkpoints are idempotent.
    base = {key: int(state.get(key) or 0) for key in run}
    errors: list[str] = []
    probes_used = 0
    checkpoint_ok = True
    exhausted = False

    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService()
    try:
        async with get_task_session() as session:
            # Bound the longest single DB op. A hung statement cannot be
            # interrupted by a loop-boundary check (gotcha: budget-guard-inner-op).
            await session.execute(text("SET statement_timeout = '60s'"))
            await session.execute(text("SET lock_timeout = '15s'"))

            rows = (
                await session.execute(
                    text(_COHORT_SQL),
                    {
                        "purge_days": PROVABLY_PURGED_AGE_DAYS,
                        "limit": limit,
                        **_cursor_params(state),
                    },
                )
            ).fetchall()

            if not rows:
                exhausted = True

            for row in rows:
                if deadline is not None and time.monotonic() >= deadline:
                    logger.info(
                        "cliff drain: caller deadline after %d outcomes",
                        run["outcomes_seen"],
                    )
                    break

                run["outcomes_seen"] += 1
                created = await _drain_one(
                    session=session,
                    service=service,
                    outcome_id=row.outcome_id,
                    ticker=row.ticker,
                    resolution_date=row.resolution_date,
                    run=run,
                    errors=errors,
                    probe_empties=probe_empties and probes_used < MAX_EXISTENCE_PROBES,
                )
                if created is None:
                    probes_used += 1

                # Advance the watermark for EVERY outcome examined, including
                # the ones that yielded nothing. That is the difference between
                # a drain and a rescan.
                state["cursor_date"] = row.resolution_date.isoformat()
                state["cursor_id"] = int(row.outcome_id)

                if run["outcomes_seen"] % CHECKPOINT_EVERY == 0:
                    await session.commit()
                    checkpoint_ok = _checkpoint(state, base, run) and checkpoint_ok
                    logger.info(
                        "cliff drain: %d outcomes, %d snapshots, "
                        "%d purged / %d present / %d unprobed empty",
                        run["outcomes_seen"], run["snapshots_created"],
                        run["empty_purged"], run["empty_present"],
                        run["empty_unprobed"],
                    )

                await asyncio.sleep(0.05)

            await session.commit()
    except Exception as exc:
        logger.error("cliff drain: run failed: %s", exc)
        errors.append(f"run_error: {str(exc)[:200]}")
    finally:
        try:
            await service.close()
        except Exception:
            pass

    checkpoint_ok = _checkpoint(state, base, run) and checkpoint_ok

    remaining = await _count_remaining(state)

    duration = round(time.monotonic() - started, 1)
    summary: dict[str, Any] = {
        "terminal": _terminal(run, exhausted, checkpoint_ok, errors),
        "run": run,
        "cumulative": {
            "outcomes_seen": state["outcomes_seen"],
            "snapshots_created": state["snapshots_created"],
            "outcomes_with_history": state["outcomes_with_history"],
            "empty_purged": state["empty_purged"],
            "empty_present": state["empty_present"],
            "empty_unprobed": state["empty_unprobed"],
            "runs": state["runs"],
        },
        "fetched": state["outcomes_seen"],
        "remaining": remaining,
        "watermark": {
            "cursor_date": state["cursor_date"],
            "cursor_id": state["cursor_id"],
            "checkpoint_written": checkpoint_ok,
        },
        "window": {
            "floor_days": PROVABLY_PURGED_AGE_DAYS,
            "at_risk_days": AT_RISK_AGE_DAYS,
        },
        "duration_s": duration,
        "errors": errors[:20],
    }
    logger.info(
        "cliff drain: terminal=%s fetched=%s remaining=%s snapshots=%d in %.1fs",
        summary["terminal"], summary["fetched"], remaining,
        run["snapshots_created"], duration,
    )
    return summary


def _terminal(
    run: dict[str, int],
    exhausted: bool,
    checkpoint_ok: bool,
    errors: list[str],
) -> str:
    """What actually happened — never "it returned" (gotcha #53).

    ``complete`` is reserved for a caught-up drain. A run that moved the
    watermark is ``partial``: real progress, not a finished job, and it must not
    read GREEN while a cohort is still expiring. A run that could not persist
    its watermark is ``failed`` even if it wrote snapshots, because the work it
    did will be done again and the progress it reports is fiction.
    """
    if not checkpoint_ok:
        return "failed"
    if any(e.startswith("run_error") for e in errors):
        return "failed"
    if exhausted and run["outcomes_seen"] == 0:
        return "complete"
    if run["outcomes_seen"] == 0:
        return "no_work"
    return "partial"


def _checkpoint(
    state: dict[str, Any], base: dict[str, int], run: dict[str, int]
) -> bool:
    """Fold this run's counters into the durable totals and persist.

    Totals are always ``base + run``, never ``state + run``. Checkpoints fire
    repeatedly within one run, so an accumulating write would count the same
    outcome once per checkpoint and inflate every number the operator reads.
    """
    for key, delta in run.items():
        state[key] = int(base.get(key) or 0) + int(delta)
    state["last_run_at"] = _now().isoformat()
    return save_state(state)


async def _count_remaining(state: dict[str, Any]) -> dict[str, Any]:
    """How much of the window is still ahead of the watermark.

    Bounded, and honest about the bound: a capped count reported as a total is
    the silent-truncation failure this codebase keeps re-learning.
    """
    try:
        async with get_task_session() as session:
            await session.execute(text("SET statement_timeout = '25s'"))
            value = (
                await session.execute(
                    text(_REMAINING_SQL),
                    {
                        "purge_days": PROVABLY_PURGED_AGE_DAYS,
                        "cap": _REMAINING_CAP,
                        **_cursor_params(state),
                    },
                )
            ).scalar()
            count = int(value or 0)
            return {
                "count": count,
                "capped": count >= _REMAINING_CAP,
                "cap": _REMAINING_CAP,
            }
    except Exception as exc:
        # An unmeasurable remaining count is reported as unmeasured, not as 0.
        logger.warning("cliff drain: remaining count failed: %s", exc)
        return {"count": None, "capped": False, "error": str(exc)[:120]}


async def _drain_one(
    *,
    session,
    service,
    outcome_id: int,
    ticker: str,
    resolution_date: datetime,
    run: dict[str, int],
    errors: list[str],
    probe_empties: bool,
) -> Optional[int]:
    """Fetch and store one outcome's history.

    Returns the number of snapshots written, or ``None`` when an existence
    probe was spent disambiguating an empty answer (so the caller can budget
    them).
    """
    if resolution_date.tzinfo is None:
        resolution_date = resolution_date.replace(tzinfo=timezone.utc)

    # Anchor the window on the market's OWN settlement. The client default
    # (now-90d .. now) barely overlaps the life of a market that settled 80
    # days ago — which is precisely the cohort this rail exists for.
    start_ts = int((resolution_date - timedelta(days=LOOKBACK_DAYS)).timestamp())
    end_ts = int((resolution_date + timedelta(days=1)).timestamp())

    try:
        candles = await service.get_market_candlesticks(
            ticker=ticker,
            period_interval=60,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        run["fetch_errors"] += 1
        errors.append(f"{ticker}: {str(exc)[:80]}")
        return 0

    if not candles:
        # gotcha #53: an empty 200 is a response SHAPE, not a fact. Only the
        # market lookup — which returns None for 404 and only for 404 —
        # distinguishes "Kalshi deleted this" from "this never traded".
        if not probe_empties:
            run["empty_unprobed"] += 1
            return 0
        try:
            market = await service.get_market(ticker)
        except Exception:
            run["empty_unprobed"] += 1
            return None
        if market is None:
            run["empty_purged"] += 1
        else:
            run["empty_present"] += 1
        return None

    batch: list[dict[str, Any]] = []
    for candle in candles:
        ts = candle.get("t")
        prob = candle.get("yes_price")
        if ts is None or prob is None:
            continue
        prob = float(prob)
        if prob <= 0 or prob >= 1:
            continue
        batch.append(
            {
                "outcome_id": outcome_id,
                "bookmaker": "kalshi",
                "probability": round(prob, 6),
                "last_price": round(prob, 4),
                "captured_at": datetime.fromtimestamp(ts, tz=timezone.utc),
            }
        )

    if not batch:
        run["empty_present"] += 1
        return 0

    for i in range(0, len(batch), 100):
        stmt = pg_insert(FuturesOddsSnapshot).values(batch[i : i + 100])
        await session.execute(stmt.on_conflict_do_nothing())

    run["snapshots_created"] += len(batch)
    run["outcomes_with_history"] += 1

    earliest = batch[0]
    await session.execute(
        text(
            """
            UPDATE futures_outcomes
            SET opening_probability = :prob,
                opening_captured_at = :ts
            WHERE id = :id AND opening_probability IS NULL
            """
        ),
        {"prob": earliest["probability"], "ts": earliest["captured_at"], "id": outcome_id},
    )
    return len(batch)


# --------------------------------------------------------------------------
# Progress, for a reader who is not running the task
# --------------------------------------------------------------------------


async def cliff_drain_progress() -> dict[str, Any]:
    """Fetched / remaining / at-risk, without running the drain."""
    state = load_state()
    remaining = await _count_remaining(state)
    cohort = await _cohort_census()
    return {
        "state": state,
        "fetched": state.get("outcomes_seen") or 0,
        "remaining": remaining,
        "cohort": cohort,
        "window": {
            "floor_days": PROVABLY_PURGED_AGE_DAYS,
            "at_risk_days": AT_RISK_AGE_DAYS,
        },
        "note": (
            "`remaining` counts what is AHEAD of the watermark inside the "
            "retention window. Outcomes behind it were examined, whether or not "
            "they yielded history — that is what makes this a drain and not a "
            "rescan. `at_risk` is the 74-86d band that expires next; anything "
            "past floor_days is unrecoverable by any rail."
        ),
    }


_CENSUS_SQL = """
    SELECT
        count(*) FILTER (
            WHERE fm.resolution_date >= now() - make_interval(days => :purge_days)
        ) AS inside_window,
        count(*) FILTER (
            WHERE fm.resolution_date >= now() - make_interval(days => :purge_days)
              AND fm.resolution_date <  now() - make_interval(days => :at_risk_days)
        ) AS at_risk,
        count(*) FILTER (
            WHERE fm.resolution_date < now() - make_interval(days => :purge_days)
        ) AS past_cliff
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi'
      AND fm.status = 'resolved'
      AND fo.external_id IS NOT NULL
      AND fm.resolution_date IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM futures_odds_snapshots fos
          WHERE fos.outcome_id = fo.id
      )
"""


async def _cohort_census() -> dict[str, Any]:
    try:
        async with get_task_session() as session:
            await session.execute(text("SET statement_timeout = '25s'"))
            row = (
                await session.execute(
                    text(_CENSUS_SQL),
                    {
                        "purge_days": PROVABLY_PURGED_AGE_DAYS,
                        "at_risk_days": AT_RISK_AGE_DAYS,
                    },
                )
            ).one()
            return {
                "inside_window": int(row.inside_window or 0),
                "at_risk": int(row.at_risk or 0),
                "past_cliff": int(row.past_cliff or 0),
            }
    except Exception as exc:
        logger.warning("cliff drain: census failed: %s", exc)
        return {"error": str(exc)[:120]}
