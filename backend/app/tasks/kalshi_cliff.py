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

Two passes, and why the drain alone was not enough (#1892, queue 359)
---------------------------------------------------------------------
The one-way watermark is the right shape for throughput and the wrong shape for
an expiring population, because the watermark and the floor move in the same
direction with the watermark in front. A row examined at 20 days old is never
looked at again and dies at 86 whether or not that one look was conclusive.
Measured 2026-08-17: **15,712** uncovered outcomes sit behind the main
watermark inside the window, matching this rail's own
``empty_present + empty_unprobed`` (15,792) to within 80 rows — i.e. the
residue is the entire population behind the cursor, and nothing revisits it.

So there is a second, smaller pass over the 74–86 day band on its own
watermark, taken FIRST. It gives every outcome exactly one more look in its
final days. The band is a sliding window, so a cursor walking it in
resolution_date ASC order takes the closest-to-death first and can never
revisit — the rows only ever leave at the old end, behind the cursor.

Convergence, not liveness (#1892, #1586)
----------------------------------------
Both of this rail's cap defects read HEALTHY from every instrument that asked
whether the task was *moving*: runs incrementing, cursors distinct,
``fetch_errors`` zero, ``wraps`` advancing. Movement is not progress. So the
summary carries ``convergence`` (is ``remaining`` FALLING, over a ring of runs)
and ``saturation`` (``outcomes_seen == limit``, and for how many runs running),
and says both out loud in ``notes``. A rail pinned at its cap and a rail
comfortably keeping up are otherwise the same reading.

MEASURED RATES, 2026-08-17 (re-measure before trusting these)
--------------------------------------------------------------
Uncovered Kalshi resolved outcomes by age, from ``/api/admin/db-query``::

    5–10d  25,964 / 45,625 (57%)     45–50d    798 / 43,168 (1.8%)
   10–15d  32,663 / 51,115 (64%)     55–60d     43 / 37,220 (0.1%)
   15–20d  24,031 / 59,717 (40%)     65–70d      0 / 35,405
   20–25d  13,713 / 53,361 (26%)     74–86d      0   <- the AT-RISK band
   25–30d   4,548 / 48,860 (9.3%)

The at-risk band is EMPTY of uncovered outcomes, so the cliff is losing ~0/day
today and the 1,100/day framing is historical. The whole backlog is young
(0–30d) and the race that matters is against INFLOW, not against the cliff:
~5,200–6,500 uncovered outcomes/day arrive, against 400/run × ~17–20 runs/day
= 6,800–8,000/day of throughput. That margin is thin, and it gets thinner the
moment #1586's capture gap closes — which is the argument for the cap, not the
cliff clock.
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

#: Share of the per-run budget reserved for the AT-RISK pass (``limit // N``),
#: and its floor. See ``_AT_RISK_SQL`` for why the reserve exists.
AT_RISK_BUDGET_DIVISOR = 4
MIN_AT_RISK_LIMIT = 25

#: How close to the floor an unexamined at-risk row has to be before its loss
#: is treated as imminent rather than merely upcoming. Two days at ~20 runs/day
#: is ~40 at-risk slices of headroom — enough that a single slow beat cannot
#: trip the alarm, small enough that the alarm still precedes the loss.
AT_RISK_GRACE_DAYS = 2

#: How many runs of (remaining, cursor) the convergence check looks back over.
#: Liveness is what made both #1892 and #1586 read healthy; a derivative needs
#: a span, and a span needs a ring.
CONVERGENCE_RING = 24

#: Per-probe statement budget when a HUMAN is waiting (the admin endpoint).
#: Heroku's router hard-caps a request at 30s and ``cliff_drain_progress``
#: fires three counts back to back; at the task path's 25s each, any two slow
#: ones H12 the endpoint — this issue's own instrument went dark that way.
PROGRESS_PROBE_TIMEOUT_S = 7

#: Per-probe statement budget inside the task, where nothing is waiting.
TASK_PROBE_TIMEOUT_S = 25


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Resumable state
# --------------------------------------------------------------------------


def _default_state() -> dict[str, Any]:
    return {
        "cursor_date": None,     # ISO resolution_date of the last outcome processed
        "cursor_id": 0,          # its outcome id — ties broken deterministically
        # The at-risk pass keeps its OWN watermark. Sharing the main one would
        # make the two passes fight over the same position and each would undo
        # the other's progress.
        "at_risk_cursor_date": None,
        "at_risk_cursor_id": 0,
        "outcomes_seen": 0,
        "snapshots_created": 0,
        "outcomes_with_history": 0,
        "empty_purged": 0,
        "empty_present": 0,
        "empty_unprobed": 0,
        # An empty answer and a degenerate one are different facts (gotcha #53
        # one level down): "Kalshi returned no candles" is about the market,
        # "every candle was 0 or 1" is about the price. Folding the second into
        # `empty_present` overstated how many markets genuinely never traded.
        "degenerate_candles": 0,
        "at_risk_outcomes_seen": 0,
        "at_risk_with_history": 0,
        "fetch_errors": 0,
        "runs": 0,
        # Consecutive runs that examined exactly `limit` outcomes. A rail
        # pinned at its cap looks identical to one comfortably keeping up.
        "cap_bound_streak": 0,
        # Bounded ring of (run, at, remaining, cursor) — the only thing that
        # can answer "is the backlog FALLING", which is the question liveness
        # cannot answer.
        "history": [],
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

# --------------------------------------------------------------------------
# The AT-RISK pass (#1892 §3)
# --------------------------------------------------------------------------
#
# The main watermark is a one-way drain: an outcome that yields nothing is
# passed PERMANENTLY. That is the right shape for throughput and the wrong
# shape for an expiring population, because the two bounds move in opposite
# directions. The watermark walks FORWARD through resolution_date (younger),
# while the retention floor walks forward behind it — so a row the main pass
# examined at 20 days old is never looked at again, and it dies at 86 days
# whether or not that single look was conclusive. Measured 2026-08-17: 15,712
# uncovered outcomes sit behind the main watermark inside the window, matching
# the drain's own `empty_present + empty_unprobed` (15,792) almost exactly.
# They are the whole residue, and by construction nothing revisits them.
#
# This pass gives every outcome exactly ONE more look, in its final days, and
# gets its budget FIRST — the guaranteed-reserve lesson from poll_kalshi, where
# the step that was promised "lazily, bounded, later" was structurally last and
# therefore never ran at all.
#
# It needs its own watermark, and the watermark is what makes it terminate. The
# band is a 12-day window that SLIDES FORWARD, so a cursor advancing through it
# in resolution_date ASC order:
#   * takes the closest-to-death first (oldest-first WITHIN the floor — gotcha
#     #41 in both directions at once), and
#   * can never revisit a row, because rows only ever leave the band at the old
#     end, which is behind the cursor.
# Caught up therefore means "no rows ahead of the at-risk cursor", not "the
# cursor reached some position" — the position it must reach moves every day.
_AT_RISK_SQL = """
    /* at_risk_pass */
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
      AND fm.resolution_date <  now() - make_interval(days => :at_risk_days)
      AND NOT EXISTS (
          SELECT 1 FROM futures_odds_snapshots fos
          WHERE fos.outcome_id = fo.id
      )
      AND (fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)
    ORDER BY fm.resolution_date ASC, fo.id ASC
    LIMIT :limit
"""

#: What is still unexamined in the band, and how much of it is out of time.
#: ``expiring_soon`` is the only number here that describes a LOSS rather than
#: a backlog: rows within ``AT_RISK_GRACE_DAYS`` of the floor that this pass
#: has not reached. Nothing recovers them afterwards, by any rail.
_AT_RISK_COUNT_SQL = """
    /* at_risk_pass_count */
    SELECT
        count(*) AS ahead,
        count(*) FILTER (
            WHERE fm.resolution_date
                  < now() - make_interval(days => :expiry_edge_days)
        ) AS expiring_soon
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi'
      AND fm.status = 'resolved'
      AND fo.external_id IS NOT NULL
      AND fm.resolution_date IS NOT NULL
      AND fm.resolution_date >= now() - make_interval(days => :purge_days)
      AND fm.resolution_date <  now() - make_interval(days => :at_risk_days)
      AND NOT EXISTS (
          SELECT 1 FROM futures_odds_snapshots fos
          WHERE fos.outcome_id = fo.id
      )
      AND (fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)
"""

#: The cold-start watermark. A ``datetime``, NOT an ISO string, and that is the
#: whole point of this comment (#1884).
#:
#: ``fm.resolution_date`` is ``DateTime(timezone=True)``, so Postgres infers
#: ``$1`` in ``(fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)`` as
#: ``timestamptz``. asyncpg is strictly typed at that boundary: handed a ``str``
#: it raises ``asyncpg.exceptions.DataError: invalid input for query argument``
#: rather than casting, which psycopg2 would have done silently. The drain
#: shipped binding the ISO string below and therefore threw on its FIRST
#: statement, every run, in 166 ms — before any fetch, so ``fetch_errors`` stayed
#: 0 and the watermark could never leave its initial value. A cold path that
#: cannot complete is the only path the rail will ever take: permanently
#: self-blocking, on a cohort that expires at ~1,100 outcomes/day.
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _as_cursor_datetime(value: Any) -> datetime:
    """State's ISO string -> the ``datetime`` asyncpg requires.

    The watermark round-trips through JSON in Redis, so it is a string by the
    time it comes back; the row that set it held a ``datetime``. Both shapes
    arrive here and both must leave as one tz-aware ``datetime``.

    Never raises (ruling 039 — a lookup must never throw). An unparseable or
    missing watermark degrades to the epoch, which costs a re-sweep of already
    barren rows; raising would cost the entire rail, which is the failure this
    function exists to end.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            logger.warning(
                "cliff drain: unparseable watermark %r — restarting at the epoch",
                value[:64],
            )
            return _EPOCH
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return _EPOCH


def _cursor_params(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "cursor_date": _as_cursor_datetime(state.get("cursor_date")),
        "cursor_id": int(state.get("cursor_id") or 0),
    }


def _at_risk_cursor_params(state: dict[str, Any]) -> dict[str, Any]:
    """Same bind contract as ``_cursor_params``, on the at-risk watermark.

    A ``datetime``, never an ISO string — the #1884 bind that self-blocked the
    whole rail for its entire life applies identically here, and a second
    watermark is a second chance to make it.
    """
    return {
        "cursor_date": _as_cursor_datetime(state.get("at_risk_cursor_date")),
        "cursor_id": int(state.get("at_risk_cursor_id") or 0),
    }


# --------------------------------------------------------------------------
# Convergence — "is it alive" is the question that hid both defects
# --------------------------------------------------------------------------


def _record_history(state: dict[str, Any], remaining: Optional[int]) -> None:
    """Append this run's (run, at, remaining, cursor) to the bounded ring."""
    ring = state.get("history")
    if not isinstance(ring, list):
        ring = []
    ring.append(
        {
            "run": int(state.get("runs") or 0),
            "at": _now().isoformat(),
            "remaining": remaining,
            "cursor_date": state.get("cursor_date"),
            "at_risk_cursor_date": state.get("at_risk_cursor_date"),
        }
    )
    state["history"] = ring[-CONVERGENCE_RING:]


def convergence(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Is ``remaining`` FALLING? Pure, so it can be tested without a database.

    This is the check both #1892 and #1586 were missing. Every instrument on
    both rails asked whether the task was moving — runs incrementing, cursors
    distinct, `fetch_errors` zero — and every one of them read healthy while
    the population they served was not being drained. Movement is not
    progress; a derivative is.

    Never raises and never guesses: fewer than two measurable samples is
    ``insufficient_data``, not an optimistic reading of one point. (#1892 was
    itself filed on a two-point "trend" that reversed sign on the third.)
    """
    try:
        points = [
            h for h in (history or [])
            if isinstance(h, dict) and isinstance(h.get("remaining"), int)
        ]
        if len(points) < 2:
            return {
                "verdict": "insufficient_data",
                "samples": len(points),
                "needed": 2,
            }
        first, last = points[0], points[-1]
        span_runs = int(last.get("run") or 0) - int(first.get("run") or 0)
        delta = int(last["remaining"]) - int(first["remaining"])
        per_run = (delta / span_runs) if span_runs > 0 else None

        span_hours = None
        try:
            t0 = datetime.fromisoformat(str(first.get("at")))
            t1 = datetime.fromisoformat(str(last.get("at")))
            span_hours = (t1 - t0).total_seconds() / 3600.0
        except Exception:
            span_hours = None
        per_day = (
            delta / (span_hours / 24.0)
            if span_hours and span_hours > 0.5
            else None
        )

        if per_run is None:
            verdict = "insufficient_data"
        elif per_run <= -1.0:
            verdict = "converging"
        elif per_run >= 1.0:
            verdict = "diverging"
        else:
            verdict = "flat"

        runs_to_empty = None
        if per_run is not None and per_run < 0:
            runs_to_empty = int(round(int(last["remaining"]) / -per_run))

        return {
            "verdict": verdict,
            "samples": len(points),
            "span_runs": span_runs,
            "span_hours": round(span_hours, 2) if span_hours else None,
            "remaining_first": int(first["remaining"]),
            "remaining_last": int(last["remaining"]),
            "delta": delta,
            "per_run": round(per_run, 1) if per_run is not None else None,
            "per_day": round(per_day, 1) if per_day is not None else None,
            "runs_to_empty": runs_to_empty,
        }
    except Exception as exc:  # pragma: no cover - a metric must never crash a rail
        logger.warning("cliff drain: convergence check failed: %s", exc)
        return {"verdict": "unmeasured", "error": str(exc)[:120]}


# --------------------------------------------------------------------------
# The drain
# --------------------------------------------------------------------------


async def run_cliff_drain(
    limit: int = 400,
    deadline: Optional[float] = None,
    probe_empties: bool = True,
    at_risk_limit: Optional[int] = None,
) -> dict[str, Any]:
    """Fetch price history for the oldest still-recoverable Kalshi outcomes.

    ``deadline`` is a ``time.monotonic()`` timestamp (the caller's budget). The
    loop checks it before every outcome — one outcome is the longest single
    uninterrupted operation here — so a truncated run banks its watermark and
    the next run continues rather than restarting (budget-guard-inner-op).

    Two passes, in this order and deliberately:

    1. **at-risk** (``at_risk_limit``, default ``limit // 4``) — the
       ``AT_RISK_AGE_DAYS``–``PROVABLY_PURGED_AGE_DAYS`` band (47–86 as measured
       2026-08-24; this docstring said 74–86 until then, and the constants are
       the authority — gotcha #35 forbids a prose day count precisely because a
       predicate cannot consume one), on its own watermark. It goes FIRST
       because it is the only work
       here that cannot be done tomorrow, and because a step promised "later,
       bounded" is a step that never runs (poll_kalshi's empty-event backfill
       is sitting on exactly that promise today).
    2. **main** (``limit``) — the one-way drain through the rest of the window.

    The returned summary carries a ``terminal`` so ``task_verdict`` can read it:
    a run that fetched nothing must not be recorded as a healthy one. It also
    carries ``convergence`` and ``saturation``, because "the task is alive" is
    the reading that let both #1892 and #1586 sit green while their populations
    were not being drained.
    """
    started = time.monotonic()
    state = load_state()
    state["runs"] = int(state.get("runs") or 0) + 1
    if not state.get("started_at"):
        state["started_at"] = _now().isoformat()

    if at_risk_limit is None:
        at_risk_limit = max(MIN_AT_RISK_LIMIT, limit // AT_RISK_BUDGET_DIVISOR)
    at_risk_limit = max(0, min(int(at_risk_limit), limit))

    run = {
        "outcomes_seen": 0,
        "outcomes_with_history": 0,
        "snapshots_created": 0,
        "empty_purged": 0,
        "empty_present": 0,
        "empty_unprobed": 0,
        "degenerate_candles": 0,
        "at_risk_outcomes_seen": 0,
        "at_risk_with_history": 0,
        "fetch_errors": 0,
    }
    # Cumulative totals as they stood BEFORE this run — the base every
    # checkpoint adds the run deltas to, so repeated checkpoints are idempotent.
    base = {key: int(state.get(key) or 0) for key in run}
    errors: list[str] = []
    probes_used = 0
    checkpoint_ok = True
    exhausted = False
    at_risk_exhausted = True

    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService()
    try:
        async with get_task_session() as session:
            # Bound the longest single DB op. A hung statement cannot be
            # interrupted by a loop-boundary check (gotcha: budget-guard-inner-op).
            await session.execute(text("SET statement_timeout = '60s'"))
            await session.execute(text("SET lock_timeout = '15s'"))

            # --- pass 1: the at-risk band, on its own watermark -------------
            if at_risk_limit > 0:
                at_risk_rows = (
                    await session.execute(
                        text(_AT_RISK_SQL),
                        {
                            "purge_days": PROVABLY_PURGED_AGE_DAYS,
                            "at_risk_days": AT_RISK_AGE_DAYS,
                            "limit": at_risk_limit,
                            **_at_risk_cursor_params(state),
                        },
                    )
                ).fetchall()
                at_risk_exhausted = len(at_risk_rows) < at_risk_limit

                for row in at_risk_rows:
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    run["at_risk_outcomes_seen"] += 1
                    before = run["outcomes_with_history"]
                    created = await _drain_one(
                        session=session,
                        service=service,
                        outcome_id=row.outcome_id,
                        ticker=row.ticker,
                        resolution_date=row.resolution_date,
                        run=run,
                        errors=errors,
                        probe_empties=(
                            probe_empties and probes_used < MAX_EXISTENCE_PROBES
                        ),
                    )
                    if created is None:
                        probes_used += 1
                    if run["outcomes_with_history"] > before:
                        run["at_risk_with_history"] += 1

                    # Advance the at-risk watermark for EVERY row examined —
                    # the band slides forward, so a row passed here can never
                    # come back into range.
                    state["at_risk_cursor_date"] = row.resolution_date.isoformat()
                    state["at_risk_cursor_id"] = int(row.outcome_id)

                    if run["at_risk_outcomes_seen"] % CHECKPOINT_EVERY == 0:
                        await session.commit()
                        checkpoint_ok = _checkpoint(state, base, run) and checkpoint_ok

                    await asyncio.sleep(0.05)

                if at_risk_rows:
                    await session.commit()
                    checkpoint_ok = _checkpoint(state, base, run) and checkpoint_ok
                    logger.info(
                        "cliff drain: at-risk pass examined %d/%d (%d yielded "
                        "history) — watermark now %s",
                        run["at_risk_outcomes_seen"], at_risk_limit,
                        run["at_risk_with_history"],
                        state.get("at_risk_cursor_date"),
                    )

            # --- pass 2: the main one-way drain -----------------------------
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
    at_risk = await _count_at_risk(state)

    cap_bound = run["outcomes_seen"] >= limit > 0
    state["cap_bound_streak"] = (
        int(state.get("cap_bound_streak") or 0) + 1 if cap_bound else 0
    )
    at_risk_cap_bound = (
        at_risk_limit > 0 and run["at_risk_outcomes_seen"] >= at_risk_limit
    )
    # The convergence ring is written AFTER the run's work and BEFORE the
    # verdict is read, so the newest point is this run's own remaining. One
    # final checkpoint persists the ring, the streak and the totals together.
    _record_history(state, remaining.get("count"))
    checkpoint_ok = _checkpoint(state, base, run) and checkpoint_ok
    conv = convergence(state.get("history") or [])

    notes: list[str] = []
    if cap_bound:
        notes.append(
            f"SATURATED: examined exactly limit={limit} for "
            f"{state['cap_bound_streak']} consecutive run(s) — throughput is "
            f"set by the cap, not by the cohort."
        )
    if cap_bound and conv.get("verdict") in ("flat", "diverging"):
        notes.append(
            "NOT CONVERGING while saturated: remaining is "
            f"{conv.get('verdict')} at {conv.get('per_run')}/run over "
            f"{conv.get('span_runs')} runs. A bounded run whose bound sits "
            "below its inflow never converges (gotcha #41)."
        )
    expiring = at_risk.get("expiring_soon")
    if isinstance(expiring, int) and expiring > 0:
        notes.append(
            f"IMMINENT LOSS: {expiring} uncovered outcome(s) are within "
            f"{AT_RISK_GRACE_DAYS}d of the {PROVABLY_PURGED_AGE_DAYS}d floor "
            "and are AHEAD of the at-risk watermark — they will expire "
            "unexamined and nothing recovers them afterwards."
        )

    duration = round(time.monotonic() - started, 1)
    summary: dict[str, Any] = {
        "terminal": _terminal(
            run, exhausted, checkpoint_ok, errors,
            at_risk_expiring=expiring, at_risk_cap_bound=at_risk_cap_bound,
        ),
        "run": run,
        "cumulative": {
            "outcomes_seen": state["outcomes_seen"],
            "snapshots_created": state["snapshots_created"],
            "outcomes_with_history": state["outcomes_with_history"],
            "empty_purged": state["empty_purged"],
            "empty_present": state["empty_present"],
            "empty_unprobed": state["empty_unprobed"],
            "degenerate_candles": state["degenerate_candles"],
            "at_risk_outcomes_seen": state["at_risk_outcomes_seen"],
            "at_risk_with_history": state["at_risk_with_history"],
            "runs": state["runs"],
        },
        "fetched": state["outcomes_seen"],
        "remaining": remaining,
        "convergence": conv,
        "saturation": {
            "limit": limit,
            "outcomes_seen": run["outcomes_seen"],
            "cap_bound": cap_bound,
            "cap_bound_streak": int(state.get("cap_bound_streak") or 0),
            "at_risk_limit": at_risk_limit,
            "at_risk_outcomes_seen": run["at_risk_outcomes_seen"],
            "at_risk_cap_bound": at_risk_cap_bound,
            "at_risk_exhausted": at_risk_exhausted,
        },
        "at_risk": at_risk,
        "watermark": {
            "cursor_date": state["cursor_date"],
            "cursor_id": state["cursor_id"],
            "at_risk_cursor_date": state["at_risk_cursor_date"],
            "at_risk_cursor_id": state["at_risk_cursor_id"],
            "checkpoint_written": checkpoint_ok,
        },
        "window": {
            "floor_days": PROVABLY_PURGED_AGE_DAYS,
            "at_risk_days": AT_RISK_AGE_DAYS,
            "grace_days": AT_RISK_GRACE_DAYS,
        },
        "duration_s": duration,
        "notes": notes,
        "errors": errors[:20],
    }
    logger.info(
        "cliff drain: terminal=%s fetched=%s remaining=%s convergence=%s "
        "(%s/run) at_risk_ahead=%s expiring=%s snapshots=%d in %.1fs",
        summary["terminal"], summary["fetched"], remaining.get("count"),
        conv.get("verdict"), conv.get("per_run"), at_risk.get("ahead"),
        expiring, run["snapshots_created"], duration,
    )
    for note in notes:
        logger.warning("cliff drain: %s", note)
    return summary


def _terminal(
    run: dict[str, int],
    exhausted: bool,
    checkpoint_ok: bool,
    errors: list[str],
    at_risk_expiring: Optional[int] = None,
    at_risk_cap_bound: bool = False,
) -> str:
    """What actually happened — never "it returned" (gotcha #53).

    ``complete`` is reserved for a caught-up drain. A run that moved the
    watermark is ``partial``: real progress, not a finished job, and it must not
    read GREEN while a cohort is still expiring. A run that could not persist
    its watermark is ``failed`` even if it wrote snapshots, because the work it
    did will be done again and the progress it reports is fiction.

    ``failed`` also covers the one condition on this rail that is a LOSS rather
    than a backlog: unexamined outcomes within the grace window of the floor,
    on a run whose at-risk pass was itself capped out. Both halves are
    required. Rows left ahead of the cursor by a pass that ran out of ROWS is
    a contradiction; rows left ahead of a pass that ran out of BUDGET is the
    rail failing at the only job that has a deadline. An unmeasurable count is
    ``None`` and never trips this — a missing probe is a finding, not a zero.
    """
    if not checkpoint_ok:
        return "failed"
    if any(e.startswith("run_error") for e in errors):
        return "failed"
    if isinstance(at_risk_expiring, int) and at_risk_expiring > 0 and at_risk_cap_bound:
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


async def _count_remaining(
    state: dict[str, Any], timeout_s: int = TASK_PROBE_TIMEOUT_S
) -> dict[str, Any]:
    """How much of the window is still ahead of the watermark.

    Bounded, and honest about the bound: a capped count reported as a total is
    the silent-truncation failure this codebase keeps re-learning. ``timeout_s``
    is smaller on the admin path, where three of these in series used to add up
    past Heroku's 30s router cap and H12 the endpoint.
    """
    try:
        async with get_task_session() as session:
            await session.execute(text(f"SET statement_timeout = '{int(timeout_s)}s'"))
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


async def _count_at_risk(
    state: dict[str, Any], timeout_s: int = TASK_PROBE_TIMEOUT_S
) -> dict[str, Any]:
    """Unexamined rows in the 74-86d band, and how many are out of time.

    ``ahead`` is a backlog — recoverable, just not yet reached.
    ``expiring_soon`` is a LOSS in progress: within ``AT_RISK_GRACE_DAYS`` of
    the floor and still unexamined. The two must never be one number, because
    only the second one has a deadline.

    Both are ``None`` on failure, never 0. A count that could not be taken and
    a count that came back empty are the same response shape (gotcha #53) and
    opposite facts — reading the emptier one as "nothing at risk" is exactly
    the false GREEN this rail exists to end.
    """
    try:
        async with get_task_session() as session:
            await session.execute(text(f"SET statement_timeout = '{int(timeout_s)}s'"))
            row = (
                await session.execute(
                    text(_AT_RISK_COUNT_SQL),
                    {
                        "purge_days": PROVABLY_PURGED_AGE_DAYS,
                        "at_risk_days": AT_RISK_AGE_DAYS,
                        "expiry_edge_days": (
                            PROVABLY_PURGED_AGE_DAYS - AT_RISK_GRACE_DAYS
                        ),
                        **_at_risk_cursor_params(state),
                    },
                )
            ).one()
            return {
                "ahead": int(row.ahead or 0),
                "expiring_soon": int(row.expiring_soon or 0),
                "grace_days": AT_RISK_GRACE_DAYS,
            }
    except Exception as exc:
        logger.warning("cliff drain: at-risk count failed: %s", exc)
        return {
            "ahead": None,
            "expiring_soon": None,
            "grace_days": AT_RISK_GRACE_DAYS,
            "error": str(exc)[:120],
        }


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
        # Candles came back and every one was degenerate (0 or 1). That is a
        # fact about the PRICE, not about whether Kalshi still holds the
        # market — counting it as `empty_present` overstated how many markets
        # genuinely never traded, on a rail whose entire purpose is keeping
        # those two apart.
        run["degenerate_candles"] += 1
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
    """Fetched / remaining / at-risk / convergence, without running the drain.

    Every probe here is bounded by :data:`PROGRESS_PROBE_TIMEOUT_S`, and the
    sum of those bounds is deliberately under Heroku's 30s router cap. The
    previous shape gave two sequential probes 25s EACH — a worst case of ~50s
    against a 30s hard cap, so once both halves were slow the endpoint could
    not succeed at all and this issue's own instrument went dark (#1892 §2).
    A slow probe now degrades to its own ``error`` field while the rest of the
    payload still answers, which is the difference between a partial reading
    and no reading.
    """
    state = load_state()
    remaining = await _count_remaining(state, timeout_s=PROGRESS_PROBE_TIMEOUT_S)
    at_risk = await _count_at_risk(state, timeout_s=PROGRESS_PROBE_TIMEOUT_S)
    cohort = await _cohort_census(timeout_s=PROGRESS_PROBE_TIMEOUT_S)
    return {
        "state": state,
        "fetched": state.get("outcomes_seen") or 0,
        "remaining": remaining,
        "at_risk": at_risk,
        "convergence": convergence(state.get("history") or []),
        "cohort": cohort,
        "window": {
            "floor_days": PROVABLY_PURGED_AGE_DAYS,
            "at_risk_days": AT_RISK_AGE_DAYS,
            "grace_days": AT_RISK_GRACE_DAYS,
        },
        "note": (
            "`remaining` counts what is AHEAD of the watermark inside the "
            "retention window. Outcomes behind it were examined, whether or not "
            "they yielded history — that is what makes this a drain and not a "
            "rescan. `at_risk` is the "
            f"{AT_RISK_AGE_DAYS}-{PROVABLY_PURGED_AGE_DAYS}d band that expires "
            "next — read it from `window` above and never from this sentence, "
            "which is why it is interpolated: it said `74-86d` until the "
            "2026-08-24 re-measurement moved the lower bound to 47 and left "
            "this note contradicting the very fields it annotates. Anything "
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


async def _cohort_census(timeout_s: int = TASK_PROBE_TIMEOUT_S) -> dict[str, Any]:
    try:
        async with get_task_session() as session:
            await session.execute(text(f"SET statement_timeout = '{int(timeout_s)}s'"))
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
