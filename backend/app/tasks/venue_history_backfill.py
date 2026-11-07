"""#11929 PR-A: keep Kalshi's own hourly prices for recently settled markets before Kalshi deletes them.

PILLAR: TRUTH. SHIP: a settled futures market keeps the price journey the venue
recorded for it. Kalshi deletes a settled market's candlesticks somewhere
between 47 and 86 days after settlement (``app/utils/kalshi_retention.py``,
``RETENTION_IS_MONOTONIC = False``). After that, only the attended #683 archive
rail can recover the history. This task saves the shortest-retention cohort
first, into ``venue_history_points``.

NOTHING READS ``venue_history_points`` YET. Serving the rows on charts is PR-B.
This module does not change ``/history``, ``/probability-timeline``,
calibration, the movers feed or any chart, and it never writes
``futures_odds_snapshots``. Those readers cannot see these rows.

OFF BY DEFAULT. Unless ``VENUE_GAP_BACKFILL_ENABLED`` is set (on
``bainluck-heavy``, which runs the ``heavy`` queue), the task returns before it
touches Redis, the database or the venue. Every bound is an env var, read at
the start of each run:

* ``VENUE_GAP_BACKFILL_ENABLED``: ``1``/``true``/``on``/``yes``/``kalshi`` = on.
* ``VENUE_GAP_BACKFILL_ROWS_PER_MIN`` (default 1000): the write rate. After
  each insert of up to :data:`INSERT_CHUNK_ROWS` rows the run sleeps until its
  rows-so-far fit the rate. A pause that would cross the wall budget ends the
  run instead.
* ``VENUE_GAP_BACKFILL_MARKETS_PER_RUN`` (default 50): markets selected per run.
* ``VENUE_GAP_BACKFILL_WALL_S`` (default 600, clamped 30..720): the run's wall
  budget. The beat fires every 15 minutes, the lease is 15 minutes, and the
  Celery soft limit is 780 s, so a run never overlaps the next.

THE COHORT, AND WHY IT IS OLDEST FIRST WITHIN A FLOOR (gotcha #41). Kalshi
markets in ``futures_markets`` with ``status = 'resolved'`` whose settlement
time is in the last :data:`CAPTURE_PLANNING_AGE_DAYS` days. The settlement time
is ``LEAST(settled_at, resolution_date)``. ``settled_at`` is when OUR poll saw
the flip, so it can be late. ``resolution_date`` is the venue's scheduled close,
which can be a padded backstop years out; ``LEAST`` takes whichever is
earlier. Ordered oldest settlement first, so the markets nearest the purge are
saved first. Never anything older than the floor, and the floor never exceeds
``PROVABLY_PURGED_AGE_DAYS``. A market already ``done``, or failed
:data:`MAX_ATTEMPTS` times, is skipped (``venue_history_backfill_progress``).

THE LEGS. The chart's own default selection (``routes/futures.py``
``_select_charted_outcome_ids``), without its read-window partition: the
:data:`TOP_LEGS` legs by ``current_probability`` plus every leg graded the
winner. Legs need a ticker, and a ticker is fetched once.

THE FETCH. Hourly candles from the market's listing (``created_at`` minus
:data:`LISTING_MARGIN`, at most :data:`MAX_LIFE` before settlement) to its
settlement, through ``KalshiAPIService.get_markets_candlesticks_raw``. Batched
up to :data:`MAX_TICKERS_PER_REQUEST` tickers within the shared 9,000-candle
budget (``futures_chart_series.ticker_batches``), keyed by the venue's own
``market_ticker`` (the response is not in request order). Paced at most one
request per :data:`REQUEST_MIN_INTERVAL_S` (2 req/s against Kalshi Basic's 20).

THE PRICE. ``kalshi_candle_price.candle_yes_price``, the calibration rails'
rule: the mid of a tight book, else the last trade, else a real one-sided
quote, else nothing. A candle with no honest price is refused, not stored,
and so is a candle after settlement or a terminal 0/1 price. An absent row is a
gap; a fabricated row would be a lie a later chart draws. Every hourly candle
that passes is stored. ``compact_series`` is a serving step (PR-B), and
compaction here would make a gap look like a flat line.

A 429 IS NEVER SWALLOWED (gotcha #36). Only ``httpx.HTTPStatusError`` and
``httpx.TransportError`` are caught around the request. A 429 records the legs
finished so far and stops the run. The next beat, 15 minutes later, is the
backoff. Any other venue error fails this market for this run
(``attempts + 1``) and the run moves on. A database error is not caught: the
run fails loudly and the next run resumes from the recorded progress.

"IT RETURNED" IS NOT "IT WORKED" (``app/utils/task_verdict.py``). The summary
carries a terminal and a ``completed``/``total`` market pair. A run that
selected nothing is ``no_work``, never a success. One verdict line is logged
per run with markets, legs, requests, rows inserted, rows already present,
refused and elapsed.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional, Protocol, Sequence

import httpx

from app.utils.futures_chart_series import (
    KALSHI_HOURLY_WHOLE_LIFE_MAX_HOURS,
    KALSHI_MAX_CANDLES_PER_REQUEST,
    ticker_batches,
)
from app.utils.kalshi_candle_price import WIDE_SPREAD_DOLLARS, candle_yes_price
from app.utils.kalshi_candle_price import _dollars as _candle_dollars
from app.utils.kalshi_retention import CAPTURE_PLANNING_AGE_DAYS, PROVABLY_PURGED_AGE_DAYS
from app.utils.task_verdict import classify_summary

logger = logging.getLogger(__name__)

#: The ``_tracked_run`` label; enrolled in ``task_verdict.ENFORCED_TASKS``.
TASK_LABEL = "venue_history_backfill"
#: The Celery task name and its single-flight lease key.
TASK_NAME = "app.tasks.backfill_venue_history_gaps"
VENUE = "kalshi"

ENABLED_ENV = "VENUE_GAP_BACKFILL_ENABLED"
ROWS_PER_MIN_ENV = "VENUE_GAP_BACKFILL_ROWS_PER_MIN"
MARKETS_PER_RUN_ENV = "VENUE_GAP_BACKFILL_MARKETS_PER_RUN"
WALL_BUDGET_ENV = "VENUE_GAP_BACKFILL_WALL_S"

DEFAULT_ROWS_PER_MIN = 1000
DEFAULT_MARKETS_PER_RUN = 50
DEFAULT_WALL_BUDGET_S = 600
ROWS_PER_MIN_BOUNDS = (1, 20_000)
MARKETS_PER_RUN_BOUNDS = (1, 500)
WALL_BUDGET_BOUNDS = (30, 720)

_ON_VALUES = frozenset({"1", "true", "on", "yes", "kalshi"})

#: Celery limits. The wall budget tops out at 720 s; one in-flight request
#: (25 s read timeout) and one insert fit before the soft limit.
SOFT_TIME_LIMIT_S = 780
TIME_LIMIT_S = 840
#: The single-flight lease outlives the hard limit, so a hard-killed run frees it
#: by expiry, and no second copy can start while a first is alive.
LEASE_TTL_S = 900

#: At most two venue requests a second.
REQUEST_MIN_INTERVAL_S = 0.5
MAX_TICKERS_PER_REQUEST = 12
TOP_LEGS = 10
PERIOD_MINUTES = 60
RESOLUTION_S = PERIOD_MINUTES * 60
MAX_ATTEMPTS = 3
INSERT_CHUNK_ROWS = 500
#: We may have first seen the market after the venue listed it; candles before
#: the real listing cost nothing but an empty stretch of the window.
LISTING_MARGIN = timedelta(days=7)
#: One ticker's whole hourly life in ONE request window (~375 days).
MAX_LIFE = timedelta(hours=KALSHI_HOURLY_WHOLE_LIFE_MAX_HOURS)
#: A market with no listing time: assume this much life.
DEFAULT_LIFE = timedelta(days=90)
STATEMENT_TIMEOUT_MS = 30_000
LOCK_TIMEOUT_MS = 5_000
MAX_ERRORS_KEPT = 10

#: Why the run stopped early, when it did.
STOP_WALL_BUDGET = "wall_budget"
STOP_ROW_THROTTLE = "row_throttle"
STOP_VENUE_429 = "venue_429"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackfillSettings:
    enabled: bool
    rows_per_min: int
    markets_per_run: int
    wall_budget_s: int


def _bounded_int(raw: Optional[str], default: int, bounds: tuple[int, int]) -> int:
    """An env integer clamped into ``bounds``; unreadable means the default."""
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default
    lo, hi = bounds
    return max(lo, min(hi, value))


def backfill_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(ENABLED_ENV, "")).strip().lower() in _ON_VALUES


def read_settings(environ: Optional[Mapping[str, str]] = None) -> BackfillSettings:
    """Every bound, read now. Called once at the start of each run."""
    env = os.environ if environ is None else environ
    return BackfillSettings(
        enabled=backfill_enabled(env),
        rows_per_min=_bounded_int(
            env.get(ROWS_PER_MIN_ENV), DEFAULT_ROWS_PER_MIN, ROWS_PER_MIN_BOUNDS
        ),
        markets_per_run=_bounded_int(
            env.get(MARKETS_PER_RUN_ENV), DEFAULT_MARKETS_PER_RUN, MARKETS_PER_RUN_BOUNDS
        ),
        wall_budget_s=_bounded_int(
            env.get(WALL_BUDGET_ENV), DEFAULT_WALL_BUDGET_S, WALL_BUDGET_BOUNDS
        ),
    )


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CohortMarket:
    market_id: int
    event_ticker: str
    settle_ts: datetime
    listed_at: Optional[datetime]
    legs_done: frozenset = frozenset()
    attempts: int = 0


@dataclass(frozen=True)
class Leg:
    outcome_id: int
    market_id: int
    ticker: Optional[str]
    current_probability: Optional[float] = None
    is_winner: Optional[bool] = None


@dataclass(frozen=True)
class VenuePoint:
    outcome_id: int
    market_id: int
    observed_at: datetime
    probability: float
    yes_bid: Optional[float]
    yes_ask: Optional[float]
    price_basis: str

    def row(self) -> dict:
        return {
            "outcome_id": self.outcome_id,
            "market_id": self.market_id,
            "venue": VENUE,
            "observed_at": self.observed_at,
            "probability": self.probability,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "price_basis": self.price_basis,
            "resolution_s": RESOLUTION_S,
        }


class VenueRateLimited(Exception):
    """The venue answered 429. The run stops; it is never retried in-run."""


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def cohort_window(now: datetime) -> tuple[datetime, datetime]:
    """``(floor, ceiling)`` on settlement time. The floor never passes the purge."""
    age_days = min(CAPTURE_PLANNING_AGE_DAYS, PROVABLY_PURGED_AGE_DAYS)
    now = _utc(now)
    return now - timedelta(days=age_days), now


def select_chart_legs(legs: Iterable[Leg], top_n: int = TOP_LEGS) -> list[Leg]:
    """The chart's default legs: top ``top_n`` by current probability, plus every winner.

    Ties break on outcome id so the choice is stable across runs. A leg without
    a ticker cannot be fetched; a ticker already chosen is not chosen twice.
    """
    usable = [leg for leg in legs if leg.ticker and str(leg.ticker).strip()]
    ranked = sorted(
        usable, key=lambda leg: (-(float(leg.current_probability or 0.0)), leg.outcome_id)
    )
    chosen: list[Leg] = []
    seen_tickers: set[str] = set()

    def _take(leg: Leg) -> None:
        if leg.ticker in seen_tickers:
            return
        seen_tickers.add(leg.ticker)
        chosen.append(leg)

    for leg in ranked:
        if len(chosen) >= top_n:
            break
        _take(leg)
    for leg in sorted(usable, key=lambda leg: leg.outcome_id):
        if leg.is_winner:
            _take(leg)
    return chosen


def request_span(market: CohortMarket) -> tuple[int, int]:
    """Unix ``(start, end)`` for the market's hourly candles: listing to settlement."""
    end = _utc(market.settle_ts)
    listed = _utc(market.listed_at)
    start = (listed - LISTING_MARGIN) if listed is not None else end - DEFAULT_LIFE
    start = max(start, end - MAX_LIFE)
    start = start.replace(minute=0, second=0, microsecond=0)
    return int(start.timestamp()), int(end.timestamp())


def request_windows(start_ts: int, end_ts: int) -> list[tuple[int, int]]:
    """Request-sized ``[start, end)`` windows; empty for an inverted span."""
    from app.tasks.event_chart_backfill import candle_windows

    return candle_windows(
        start_ts,
        end_ts,
        period_minutes=PERIOD_MINUTES,
        max_periods=KALSHI_MAX_CANDLES_PER_REQUEST,
    )


def leg_groups(tickers: Sequence[str], start_ts: int, end_ts: int) -> list[list[str]]:
    """Ticker groups that fit the shared candle budget, at most 12 per request."""
    periods = max(1, min(KALSHI_MAX_CANDLES_PER_REQUEST, math.ceil((end_ts - start_ts) / RESOLUTION_S)))
    groups: list[list[str]] = []
    for group in ticker_batches(list(tickers), periods=periods):
        for i in range(0, len(group), MAX_TICKERS_PER_REQUEST):
            groups.append(group[i:i + MAX_TICKERS_PER_REQUEST])
    return groups


def _book_value(value: Optional[float]) -> Optional[float]:
    if value is None or not (0.0 <= value <= 1.0):
        return None
    return round(value, 6)


def price_basis(candle: dict, price: float) -> str:
    """Which part of the candle ``candle_yes_price`` took the price from. A label only."""
    bid = _candle_dollars(candle.get("yes_bid"), "close_dollars")
    ask = _candle_dollars(candle.get("yes_ask"), "close_dollars")
    last = _candle_dollars(
        candle.get("price"), "close_dollars", "mean_dollars", "previous_dollars"
    )
    if (
        bid is not None and ask is not None and bid > 0 and ask > 0
        and ask >= bid and (ask - bid) <= WIDE_SPREAD_DOLLARS
        and math.isclose(price, (bid + ask) / 2.0, abs_tol=1e-9)
    ):
        return "mid"
    if last is not None and math.isclose(price, last, abs_tol=1e-9):
        return "last_trade"
    if bid is not None and math.isclose(price, bid, abs_tol=1e-9):
        return "bid"
    if ask is not None and math.isclose(price, ask, abs_tol=1e-9):
        return "ask"
    return "mid"


def candle_point(
    candle: Any, *, outcome_id: int, market_id: int, settle_ts: datetime
) -> tuple[Optional[VenuePoint], Optional[str]]:
    """One candle → a point, or ``(None, reason)`` when there is no honest price."""
    if not isinstance(candle, dict):
        return None, "malformed"
    raw_ts = candle.get("end_period_ts")
    try:
        observed_at = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None, "no_timestamp"
    # Strict, as the #683 archive store's CHECK (`interval_end < venue_settlement_ts`):
    # a candle ending at or after settlement is not a pre-resolution price.
    if observed_at >= _utc(settle_ts):
        return None, "post_settlement"
    price = candle_yes_price(candle)
    if price is None:
        return None, "no_price"
    probability = round(float(price), 6)
    if not (0.0 < probability < 1.0):
        return None, "terminal"
    return VenuePoint(
        outcome_id=outcome_id,
        market_id=market_id,
        observed_at=observed_at,
        probability=probability,
        yes_bid=_book_value(_candle_dollars(candle.get("yes_bid"), "close_dollars")),
        yes_ask=_book_value(_candle_dollars(candle.get("yes_ask"), "close_dollars")),
        price_basis=price_basis(candle, float(price)),
    ), None


# ---------------------------------------------------------------------------
# Pacing, throttle and wall budget
# ---------------------------------------------------------------------------


class RunClock:
    """The run's three bounds: venue pacing, the row rate and the wall budget.

    ``clock`` is monotonic seconds and ``sleep`` an awaitable, both injectable,
    so a test drives a fake clock and never waits.
    """

    def __init__(
        self,
        *,
        wall_budget_s: float,
        rows_per_min: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        min_request_interval_s: float = REQUEST_MIN_INTERVAL_S,
    ):
        self._clock = clock
        self._sleep = sleep
        self.started = clock()
        self.deadline = self.started + float(wall_budget_s)
        self.rows_per_min = max(1, int(rows_per_min))
        self.min_request_interval_s = float(min_request_interval_s)
        self.rows = 0
        self.slept_s = 0.0
        self._last_request: Optional[float] = None

    def now(self) -> float:
        return self._clock()

    def elapsed(self) -> float:
        return self._clock() - self.started

    def expired(self) -> bool:
        return self._clock() >= self.deadline

    async def _pause(self, seconds: float) -> bool:
        if seconds <= 0:
            return True
        if self._clock() + seconds > self.deadline:
            return False
        self.slept_s += seconds
        await self._sleep(seconds)
        return True

    async def before_request(self) -> bool:
        """Wait out the pacing gap. False when the wall budget is spent."""
        if self._last_request is not None:
            gap = self._last_request + self.min_request_interval_s - self._clock()
            if not await self._pause(gap):
                return False
        if self.expired():
            return False
        self._last_request = self._clock()
        return True

    async def after_rows(self, count: int) -> bool:
        """Sleep until the run's rows fit the rate. False when that crosses the budget."""
        self.rows += max(0, int(count))
        due = self.started + self.rows * 60.0 / self.rows_per_min
        return await self._pause(due - self._clock())


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class BackfillStore(Protocol):
    async def select_cohort(
        self, *, floor: datetime, ceiling: datetime, limit: int, max_attempts: int
    ) -> list[CohortMarket]: ...

    async def load_legs(self, market_ids: Sequence[int]) -> dict[int, list[Leg]]: ...

    async def insert_points(self, points: Sequence[VenuePoint]) -> int: ...

    async def record_progress(
        self,
        market_id: int,
        *,
        status: str,
        legs_done: Iterable[int],
        attempts_inc: int,
        points_inserted: int,
        last_error: Optional[str],
    ) -> None: ...


#: The cohort read. ``fm.settled_at >= :floor`` is implied by the LEAST bound
#: (LEAST <= settled_at) and is there so the planner can use the
#: ``settled_at`` index instead of scanning every Kalshi market.
COHORT_SQL = """
SELECT fm.id AS market_id,
       fm.external_id AS event_ticker,
       fm.created_at AS listed_at,
       LEAST(fm.settled_at, fm.resolution_date) AS settle_ts,
       COALESCE(p.legs_done, '{}'::integer[]) AS legs_done,
       COALESCE(p.attempts, 0) AS attempts
FROM futures_markets fm
LEFT JOIN venue_history_backfill_progress p
       ON p.venue = :venue AND p.market_id = fm.id
WHERE fm.source = 'kalshi'
  AND fm.status = 'resolved'
  AND fm.settled_at IS NOT NULL
  AND fm.settled_at >= :floor
  AND LEAST(fm.settled_at, fm.resolution_date) >= :floor
  AND LEAST(fm.settled_at, fm.resolution_date) <= :ceiling
  AND (p.market_id IS NULL OR (p.status <> 'done' AND p.attempts < :max_attempts))
ORDER BY settle_ts ASC, fm.id ASC
LIMIT :limit
"""

LEGS_SQL = """
SELECT fo.id AS outcome_id, fo.market_id, fo.external_id AS ticker,
       fo.current_probability, fo.is_winner
FROM futures_outcomes fo
WHERE fo.market_id = ANY(:market_ids)
"""


class PgStore:
    """The production store: one session, a commit after every statement.

    Committing after each read and write means no transaction is open while
    the run waits on the venue or sleeps for the throttle.
    """

    def __init__(self, session: Any):
        self.session = session

    async def select_cohort(
        self, *, floor: datetime, ceiling: datetime, limit: int, max_attempts: int
    ) -> list[CohortMarket]:
        from sqlalchemy import text

        result = await self.session.execute(
            text(COHORT_SQL),
            {
                "venue": VENUE,
                "floor": floor,
                "ceiling": ceiling,
                "limit": int(limit),
                "max_attempts": int(max_attempts),
            },
        )
        rows = result.mappings().all()
        await self.session.commit()
        return [
            CohortMarket(
                market_id=int(r["market_id"]),
                event_ticker=r["event_ticker"],
                settle_ts=_utc(r["settle_ts"]),
                listed_at=_utc(r["listed_at"]),
                legs_done=frozenset(int(x) for x in (r["legs_done"] or [])),
                attempts=int(r["attempts"] or 0),
            )
            for r in rows
        ]

    async def load_legs(self, market_ids: Sequence[int]) -> dict[int, list[Leg]]:
        from sqlalchemy import text

        if not market_ids:
            return {}
        result = await self.session.execute(
            text(LEGS_SQL), {"market_ids": [int(m) for m in market_ids]}
        )
        rows = result.mappings().all()
        await self.session.commit()
        out: dict[int, list[Leg]] = {}
        for r in rows:
            prob = r["current_probability"]
            out.setdefault(int(r["market_id"]), []).append(
                Leg(
                    outcome_id=int(r["outcome_id"]),
                    market_id=int(r["market_id"]),
                    ticker=r["ticker"],
                    current_probability=float(prob) if prob is not None else None,
                    is_winner=r["is_winner"],
                )
            )
        return out

    async def insert_points(self, points: Sequence[VenuePoint]) -> int:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.models.models import VenueHistoryPoint

        if not points:
            return 0
        table = VenueHistoryPoint.__table__
        stmt = (
            pg_insert(table)
            .values([p.row() for p in points])
            .on_conflict_do_nothing(index_elements=["outcome_id", "observed_at"])
            .returning(table.c.id)
        )
        result = await self.session.execute(stmt)
        inserted = len(result.fetchall())
        await self.session.commit()
        return inserted

    async def record_progress(
        self,
        market_id: int,
        *,
        status: str,
        legs_done: Iterable[int],
        attempts_inc: int,
        points_inserted: int,
        last_error: Optional[str],
    ) -> None:
        from sqlalchemy import func
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.models.models import VenueHistoryBackfillProgress

        table = VenueHistoryBackfillProgress.__table__
        stmt = pg_insert(table).values(
            venue=VENUE,
            market_id=int(market_id),
            status=status,
            legs_done=sorted(int(x) for x in legs_done),
            attempts=int(attempts_inc),
            points_inserted=int(points_inserted),
            last_error=(last_error[:500] if last_error else None),
            completed_at=func.now() if status == "done" else None,
        )
        # `updated_at` comes from its server default and, on conflict, from
        # EXCLUDED (that same default), so this writer never names a touch-stamp
        # (`tests/test_futures_stamp_semantics.py` audits `updated_at = now()`
        # writers; this table is not one of the futures tables it guards).
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.venue, table.c.market_id],
            set_={
                "status": excluded.status,
                "legs_done": excluded.legs_done,
                "attempts": table.c.attempts + excluded.attempts,
                "points_inserted": table.c.points_inserted + excluded.points_inserted,
                "last_error": excluded.last_error,
                "updated_at": excluded.updated_at,
                "completed_at": func.coalesce(table.c.completed_at, excluded.completed_at),
            },
        )
        await self.session.execute(stmt)
        await self.session.commit()


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def new_summary(settings: BackfillSettings) -> dict:
    return {
        "task": TASK_LABEL,
        "venue": VENUE,
        "terminal": None,
        "completed": 0,          # markets finished this run
        "total": 0,              # markets selected this run
        "markets_failed": 0,
        "markets_no_legs": 0,
        "legs": 0,               # chart legs on the selected markets
        "legs_fetched": 0,       # legs whose whole life was fetched this run
        "legs_empty": 0,         # of those, legs the venue returned no price for
        "requests": 0,
        "rows_inserted": 0,
        "rows_present": 0,       # already stored (ON CONFLICT DO NOTHING)
        "refused": {},
        "refused_total": 0,
        "unrequested_tickers": 0,
        "stopped_by": None,
        "errors": [],
        "elapsed_s": 0.0,
        "throttle_sleep_s": 0.0,
        "settings": {
            "rows_per_min": settings.rows_per_min,
            "markets_per_run": settings.markets_per_run,
            "wall_budget_s": settings.wall_budget_s,
        },
    }




@dataclass
class _MarketResult:
    done: bool = False
    failed: bool = False
    stop: Optional[str] = None
    legs_done: set = field(default_factory=set)


#: Group outcomes from :func:`_backfill_market`'s inner fetch.
_GROUP_COMPLETE = "complete"
_GROUP_COMPLETE_THEN_STOP = "complete_then_stop"
_GROUP_INCOMPLETE_STOP = "incomplete_stop"
_GROUP_FAILED = "failed"


async def _backfill_market(
    market: CohortMarket,
    legs: list[Leg],
    *,
    store: BackfillStore,
    service: Any,
    rc: RunClock,
    summary: dict,
) -> _MarketResult:
    """Fetch and store one market's chart legs, resuming after ``legs_done``.

    Progress is recorded after a group of legs is fully written, when the run
    stops partway, and on a venue failure. It is never recorded for a leg
    whose windows were not all fetched, so a resumed run refetches that leg
    (its stored rows conflict and are counted as already present).
    """
    res = _MarketResult(legs_done=set(market.legs_done))
    chart_legs = select_chart_legs(legs)
    summary["legs"] += len(chart_legs)
    if not chart_legs:
        summary["markets_no_legs"] += 1
    pending = [leg for leg in chart_legs if leg.outcome_id not in res.legs_done]
    written = {"points": 0}

    async def _record(status: str, *, attempts_inc: int = 0, error: Optional[str] = None) -> None:
        await store.record_progress(
            market.market_id,
            status=status,
            legs_done=res.legs_done,
            attempts_inc=attempts_inc,
            points_inserted=written["points"],
            last_error=error,
        )
        written["points"] = 0

    if not pending:
        await _record("done")
        res.done = True
        return res

    start_ts, end_ts = request_span(market)
    windows = request_windows(start_ts, end_ts)
    by_ticker = {leg.ticker: leg for leg in pending}

    async def _fetch_group(group: list[str], points_by_leg: dict[int, int]) -> tuple[str, Optional[str]]:
        for w_index, (window_start, window_end) in enumerate(windows):
            if not await rc.before_request():
                return _GROUP_INCOMPLETE_STOP, STOP_WALL_BUDGET
            summary["requests"] += 1
            try:
                candles_by_ticker = await service.get_markets_candlesticks_raw(
                    tickers=group,
                    period_interval=PERIOD_MINUTES,
                    start_ts=window_start,
                    end_ts=window_end,
                )
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code == 429:
                    raise VenueRateLimited(f"{market.event_ticker}: 429") from exc
                return _GROUP_FAILED, f"http_{code}"
            except httpx.TransportError as exc:
                return _GROUP_FAILED, type(exc).__name__

            points: dict[tuple[int, datetime], VenuePoint] = {}
            for ticker, candles in (candles_by_ticker or {}).items():
                leg = by_ticker.get(ticker)
                if leg is None or ticker not in group:
                    # Keyed by the venue's own ticker; one we did not ask for in
                    # this request is never filed under any leg.
                    summary["unrequested_tickers"] += 1
                    continue
                for candle in candles or []:
                    point, reason = candle_point(
                        candle,
                        outcome_id=leg.outcome_id,
                        market_id=market.market_id,
                        settle_ts=market.settle_ts,
                    )
                    if point is None:
                        summary["refused"][reason] = summary["refused"].get(reason, 0) + 1
                        summary["refused_total"] += 1
                        continue
                    points[(point.outcome_id, point.observed_at)] = point
            ordered = sorted(points.values(), key=lambda p: (p.outcome_id, p.observed_at))
            for p in ordered:
                points_by_leg[p.outcome_id] += 1

            chunks = [
                ordered[i:i + INSERT_CHUNK_ROWS]
                for i in range(0, len(ordered), INSERT_CHUNK_ROWS)
            ]
            for c_index, chunk in enumerate(chunks):
                inserted = await store.insert_points(chunk)
                summary["rows_inserted"] += inserted
                summary["rows_present"] += len(chunk) - inserted
                written["points"] += inserted
                if not await rc.after_rows(len(chunk)):
                    last = w_index == len(windows) - 1 and c_index == len(chunks) - 1
                    return (
                        _GROUP_COMPLETE_THEN_STOP if last else _GROUP_INCOMPLETE_STOP,
                        STOP_ROW_THROTTLE,
                    )
        return _GROUP_COMPLETE, None

    for group in leg_groups([leg.ticker for leg in pending], start_ts, end_ts):
        points_by_leg = {by_ticker[t].outcome_id: 0 for t in group}
        try:
            state, detail = await _fetch_group(group, points_by_leg)
        except VenueRateLimited:
            await _record("in_progress")
            raise
        if state == _GROUP_FAILED:
            await _record("failed", attempts_inc=1, error=detail)
            summary["errors"].append(f"{market.market_id}:{detail}")
            res.failed = True
            return res
        if state == _GROUP_INCOMPLETE_STOP:
            res.stop = detail
            await _record("in_progress")
            return res
        res.legs_done.update(points_by_leg)
        summary["legs_fetched"] += len(points_by_leg)
        summary["legs_empty"] += sum(1 for n in points_by_leg.values() if n == 0)
        if state == _GROUP_COMPLETE_THEN_STOP:
            res.stop = detail
            break

    if res.stop and any(leg.outcome_id not in res.legs_done for leg in pending):
        await _record("in_progress")
        return res
    await _record("done")
    res.done = True
    return res


def _terminal(summary: dict) -> str:
    if summary["total"] == 0:
        return "no_work"
    if summary["stopped_by"] == STOP_VENUE_429:
        return "partial"
    if summary["completed"] < summary["total"]:
        return "partial"
    return "complete"


async def backfill_once(
    store: BackfillStore,
    service: Any,
    settings: BackfillSettings,
    *,
    now: datetime,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> dict:
    """One bounded run over the cohort. Returns the summary ``_tracked_run`` grades."""
    summary = new_summary(settings)
    rc = RunClock(
        wall_budget_s=settings.wall_budget_s,
        rows_per_min=settings.rows_per_min,
        clock=clock,
        sleep=sleep,
    )
    floor, ceiling = cohort_window(now)
    summary["cohort_floor"] = floor.isoformat()
    summary["cohort_ceiling"] = ceiling.isoformat()

    markets = await store.select_cohort(
        floor=floor,
        ceiling=ceiling,
        limit=settings.markets_per_run,
        max_attempts=MAX_ATTEMPTS,
    )
    summary["total"] = len(markets)
    legs_by_market = await store.load_legs([m.market_id for m in markets]) if markets else {}

    for market in markets:
        if rc.expired():
            summary["stopped_by"] = STOP_WALL_BUDGET
            break
        try:
            res = await _backfill_market(
                market,
                legs_by_market.get(market.market_id, []),
                store=store,
                service=service,
                rc=rc,
                summary=summary,
            )
        except VenueRateLimited as exc:
            summary["stopped_by"] = STOP_VENUE_429
            summary["errors"].append(str(exc))
            break
        if res.done:
            summary["completed"] += 1
        if res.failed:
            summary["markets_failed"] += 1
        if res.stop:
            summary["stopped_by"] = res.stop
            break

    summary["errors"] = summary["errors"][:MAX_ERRORS_KEPT]
    summary["elapsed_s"] = round(rc.elapsed(), 3)
    summary["throttle_sleep_s"] = round(rc.slept_s, 3)
    summary["terminal"] = _terminal(summary)
    verdict = classify_summary(summary)
    summary["verdict"] = verdict.verdict
    logger.info(
        "venue_history_backfill verdict=%s terminal=%s markets=%d/%d failed=%d legs=%d "
        "legs_fetched=%d legs_empty=%d requests=%d rows_inserted=%d rows_present=%d "
        "refused=%d stopped_by=%s elapsed=%.1fs",
        verdict.verdict,
        summary["terminal"],
        summary["completed"],
        summary["total"],
        summary["markets_failed"],
        summary["legs"],
        summary["legs_fetched"],
        summary["legs_empty"],
        summary["requests"],
        summary["rows_inserted"],
        summary["rows_present"],
        summary["refused_total"],
        summary["stopped_by"],
        summary["elapsed_s"],
    )
    return summary


async def run_venue_history_backfill(
    *,
    environ: Optional[Mapping[str, str]] = None,
    store: Optional[BackfillStore] = None,
    service: Any = None,
    now: Optional[datetime] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> dict:
    """The task body. Off: returns before any database, Redis or venue work."""
    settings = read_settings(environ)
    if not settings.enabled:
        return {"task": TASK_LABEL, "status": "disabled", "terminal": "skipped"}

    own_service = service is None
    if own_service:
        from app.services.kalshi_api import KalshiAPIService

        service = KalshiAPIService()
    try:
        run_now = _utc(now) if now is not None else datetime.now(timezone.utc)
        if store is not None:
            return await backfill_once(
                store, service, settings, now=run_now, clock=clock, sleep=sleep
            )
        from app.tasks.base import get_task_session

        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            return await backfill_once(
                PgStore(session), service, settings, now=run_now, clock=clock, sleep=sleep
            )
    finally:
        if own_service:
            await service.close()
