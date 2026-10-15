"""#683 archive recovery: a bounded, read-only, exact-ID DRY-RUN planner.

PILLAR: TRUTH. SHIP: settled Kalshi questions that have no price history get
back their real pre-resolution probability timeline, and archive provenance stays
separate from live capture.

This module READS. It selects stored Kalshi outcomes that have zero snapshots,
asks Kalshi's historical tier about each one by its exact stored ticker, and
returns the plan :mod:`app.utils.kalshi_archive_history` decides. It writes
nothing to the database, Redis or the scheduler. It has no apply path, so
"disabled" is structural, not a flag someone can flip. Entry point:
``backend/scripts/kalshi_archive_recovery_dry_run.py``.

WHY THERE IS NO WRITE PATH YET. It is a schema decision, and the decision belongs
to Goal Root, not this slice. ``futures_odds_snapshots`` has no provenance column
other than ``bookmaker`` and no unique key, so ``ON CONFLICT DO NOTHING`` there
dedups nothing. Every calibration phase also reads it WITHOUT a bookmaker filter.
Part A bounds by ``LEAST(start, resolution)``. Part B takes the first snapshot at
least an hour after the opening and applies NO cutoff at all
(``tasks/backfill_winners.py``). So a ``reader_only`` archive row written there
WOULD reach calibration, and an archive row written as ``bookmaker='kalshi'``
would be indistinguishable from live capture. Both break this ship's own terms.
The plan therefore carries full provenance per row, and the write waits for one of:
(a) a provenance column on snapshots plus an exclusion in every calibration
lateral (a migration, attended), (b) a separate archive table that readers union
and calibration reads only for ``forecast`` rows (a migration, attended), or
(c) ``bookmaker='kalshi_archive'`` plus an exclusion clause in every calibration
reader (no migration, but every reader must change in the same release).

BOUNDS, all enforced here and none of them a guess at Kalshi's rate budget:
at most :data:`MAX_OUTCOMES` outcomes and :data:`MAX_REQUESTS` GETs per run,
at least :data:`MIN_PACE_SECONDS` between GETs, and a wall-clock deadline. It
also honours the shared Kalshi cooldown that the trade rail records
(``_TRADE_BACKFILL_COOLDOWN_KEY``). It reads that key and never writes it. A 429
is waited out once, but only when ``Retry-After`` fits
``_TRADE_429_MAX_WAIT_S`` and the deadline. Otherwise the run stops, with the
cursor held BEFORE the refused outcome. A 429 is never recorded as "no data".
The deadline is re-checked after every pacing or 429 sleep, before the next GET.

WHAT IS NEVER WRITTEN DOWN AS DONE. A listing the run could not finish (budget,
429) holds the outcome with its listing cursor in ``held_outcome``; only an
exhausted listing can say a ticker is absent. A malformed 200 (wrong body, a
row that is not a market, a repeated cursor) is an error and leaves the outcome
owed. A long history is read in several windows at one width, and a run that
stops between them holds the outcome with the unread windows named. An outcome
whose opening is unknown is planned ``incomplete`` with the earlier gap owed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Optional, Sequence

from sqlalchemy import text

from app.utils.kalshi_archive_history import (
    COVERAGE_COMPLETE,
    COVERAGE_INCOMPLETE,
    OWED_MALFORMED_CANDLES,
    ROUTE_ARCHIVE,
    OutcomePlan,
    archive_settled_cutoff,
    candle_is_wellformed,
    choose_period,
    classify_candles,
    forecast_cutoff,
    identity_refusal,
    importable,
    owed_window,
    parse_instant,
    plan_digest,
    request_windows,
    route_market,
)

logger = logging.getLogger(__name__)

#: Hard ceilings. The caller may ask for less and is clamped to these if it asks for more.
MAX_OUTCOMES = 200
MAX_REQUESTS = 400
MIN_PACE_SECONDS = 0.5
#: Rows per listing page. There is NO per-event page cap: an event's listing is
#: paged until the stored ticker is found or the listing is exhausted, inside the
#: run's request budget and deadline. A listing the run could not finish is never
#: read as absence. The outcome is held, with the listing cursor reported.
LISTING_PAGE_LIMIT = 200
#: Stored outcome tickers this arm will ask about: the exact ``KX…-…-…`` shape the
#: trade rail already selects on. Passed as a bind, never inlined (gotcha #45).
TICKER_LIKE = "KX%-%-%"

#: Zero-snapshot Kalshi outcomes with an exact stored ticker. ``{id_clause}`` is
#: one of two fixed strings, never caller text:
#:
#: - keyset (broad discovery) also requires ``status='resolved'`` and a
#:   ``resolution_date`` BACKSTOP before the archive cutoff (or none). That keeps
#:   discovery bounded, and it UNDER-covers: an early-finalized market can carry a
#:   future backstop, and a settled one can still read ``open`` (gotcha #33). The
#:   report names this limit; those outcomes are reached by exact id.
#: - exact ids read the stored identity with NEITHER local filter. Neither field is
#:   the venue's settlement, so the venue's own ``settlement_ts`` and the provider
#:   cutoff choose the tier (``identity_refusal`` + ``route_market``).
CANDIDATE_SQL = """
    SELECT fo.id AS outcome_id,
           fo.external_id AS ticker,
           fm.external_id AS event_ticker,
           fm.resolution_date AS resolution_date,
           (e.id IS NOT NULL) AS has_event,
           e.commence_time AS commence_time,
           e.commence_time_source AS commence_time_source,
           e.created_at AS created_at,
           e.completed_at AS completed_at
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    LEFT JOIN events e ON e.id = fm.event_id
    WHERE fm.source = 'kalshi'
      AND fo.external_id LIKE :ticker_like
      AND fm.external_id IS NOT NULL
      AND COALESCE(fo.resolution_source, '') NOT IN
          ('no_pregame_trading', 'did_not_play', 'withdrew')
      AND NOT EXISTS (
          SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
      )
      AND {id_clause}
    ORDER BY fo.id ASC
    LIMIT :lim
"""
_ID_AFTER = (
    "fm.status = 'resolved'"
    " AND (fm.resolution_date IS NULL OR fm.resolution_date < :archive_cutoff)"
    " AND fo.id > :after_id"
)
_ID_EXACT = "fo.id = ANY(:outcome_ids)"

#: What keyset discovery cannot see, stated in every keyset report.
KEYSET_SELECTOR_LIMITS = (
    "excludes outcomes whose market is not status='resolved' locally",
    "excludes outcomes whose resolution_date backstop is at or after the archive cutoff",
    "an early-finalized market can fall in either group; name it with --outcome-ids",
)

STORED_INSTANTS_SQL = """
    SELECT outcome_id, captured_at
    FROM futures_odds_snapshots
    WHERE outcome_id = ANY(:ids)
"""


class _RateLimited(Exception):
    def __init__(self, wait: float):
        super().__init__(f"429, cooldown {wait:.1f}s")
        self.wait = wait


class _BudgetSpent(Exception):
    pass


class _ListingUnreadable(Exception):
    """This event's listing failed earlier in the run; siblings stay owed too."""


@dataclass
class _Listing:
    """One event's archive listing as far as this run has read it."""

    markets: dict = field(default_factory=dict)
    cursor: Optional[str] = None
    pages: int = 0
    exhausted: bool = False
    error: Optional[str] = None
    seen_cursors: set = field(default_factory=set)


def _read_shared_cooldown() -> Optional[float]:
    """Seconds left on the trade rail's shared Kalshi cooldown; ``None`` if unreadable."""
    try:
        from app.tasks.kalshi import _TRADE_BACKFILL_COOLDOWN_KEY, _trade_cooldown_clock
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(_TRADE_BACKFILL_COOLDOWN_KEY)
        return float(raw or 0) - _trade_cooldown_clock()
    except Exception as e:  # advisory read; reported, never fatal
        logger.info("archive dry-run: shared cooldown unreadable (%s)", e)
        return None


def _default_session_factory():
    from app.tasks.base import get_task_session

    return get_task_session()


def _default_service_factory():
    from app.services.kalshi_api import KalshiAPIService

    return KalshiAPIService()


def _default_429_wait(exc: BaseException) -> Optional[float]:
    from app.tasks.kalshi import _kalshi_trade_429_wait

    return _kalshi_trade_429_wait(exc)


def _default_max_wait() -> float:
    from app.tasks.kalshi import _TRADE_429_MAX_WAIT_S

    return _TRADE_429_MAX_WAIT_S


async def plan_archive_recovery(
    *,
    limit: int = 50,
    after_id: int = 0,
    outcome_ids: Optional[Sequence[int]] = None,
    max_requests: int = 60,
    pace_seconds: float = 1.0,
    deadline_seconds: float = 600.0,
    session_factory: Callable[[], Any] = _default_session_factory,
    service_factory: Callable[[], Any] = _default_service_factory,
    cooldown_reader: Callable[[], Optional[float]] = _read_shared_cooldown,
    rate_limit_wait: Callable[[BaseException], Optional[float]] = _default_429_wait,
    max_wait_seconds: Optional[float] = None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Plan, never write. Returns a JSON-serialisable report (see module doc)."""
    limit = max(1, min(int(limit), MAX_OUTCOMES))
    max_requests = max(1, min(int(max_requests), MAX_REQUESTS))
    pace_seconds = max(float(pace_seconds), MIN_PACE_SECONDS)
    # An override may shorten the house 429 wait ceiling, never raise it.
    house_max_wait = _default_max_wait()
    max_wait = (
        house_max_wait
        if max_wait_seconds is None
        else min(float(max_wait_seconds), house_max_wait)
    )
    exact = [int(i) for i in outcome_ids][:limit] if outcome_ids else None
    deadline = monotonic() + max(float(deadline_seconds), 0.0)

    report: dict = {
        "mode": "dry_run",
        "writes": 0,
        "selection": "exact_ids" if exact is not None else "keyset_after_id",
        "after_id": None if exact is not None else int(after_id),
        "limit": limit,
        "max_requests": max_requests,
        "pace_seconds": pace_seconds,
        "requests_sent": 0,
        "rate_limit_waits": 0,
        "archive_cutoff": None,
        "candidates": 0,
        "planned": 0,
        "owed_ids": [],
        "incomplete_ids": [],
        "held_outcome": None,
        "errors": [],
        "plans": [],
        "totals": {},
        "importable_points": 0,
        "plan_digest": None,
        "next_after_id": None if exact is not None else int(after_id),
        "terminal": None,
    }
    if exact is None:
        report["selector_limits"] = list(KEYSET_SELECTOR_LIMITS)

    cooldown_left = cooldown_reader()
    report["shared_cooldown_s"] = (
        "unreadable" if cooldown_left is None else round(max(cooldown_left, 0.0), 1)
    )
    if cooldown_left is not None and cooldown_left > 0:
        report["terminal"] = "cooldown"
        return report

    state = {"sent": 0}

    def _spent() -> bool:
        return state["sent"] >= max_requests or monotonic() >= deadline

    async def _get(call: Callable[[], Awaitable[Any]]) -> Any:
        for attempt in range(2):
            if _spent():
                raise _BudgetSpent()
            if state["sent"]:
                await sleep(pace_seconds)
                # The pace (and a 429 wait before it) spends wall time: re-check,
                # so no GET leaves after the run's stated deadline.
                if _spent():
                    raise _BudgetSpent()
            state["sent"] += 1
            report["requests_sent"] = state["sent"]
            try:
                return await _within_deadline(call)
            except Exception as e:
                wait = rate_limit_wait(e)
                if wait is None:
                    raise
                left = deadline - monotonic()
                if attempt == 0 and wait <= max_wait and wait < left:
                    report["rate_limit_waits"] += 1
                    await sleep(wait)
                    continue
                raise _RateLimited(wait) from e
        raise AssertionError("unreachable")

    async def _within_deadline(call: Callable[[], Awaitable[Any]]) -> Any:
        """Await one GET for at most the time left; on expiry cancel it, stop partial.

        ``asyncio.wait`` (not ``wait_for``) so only OUR deadline reads as a budget
        stop. A timeout raised by the call itself stays an ordinary owed error.
        """
        task = asyncio.ensure_future(call())
        done, _ = await asyncio.wait({task}, timeout=max(deadline - monotonic(), 0.0))
        if task in done:
            return task.result()
        task.cancel()
        # Collect the cancelled GET (its outcome is not evidence) without
        # swallowing a cancellation of the planner itself.
        await asyncio.gather(task, return_exceptions=True)
        raise _BudgetSpent()

    service = service_factory()
    try:
        try:
            cutoff_payload = await _get(service.get_historical_cutoff)
        except (_BudgetSpent, _RateLimited) as e:
            report["terminal"] = (
                "rate_limited" if isinstance(e, _RateLimited) else "partial"
            )
            if isinstance(e, _RateLimited):
                report["stopped_on_cooldown_s"] = e.wait
            return report
        except Exception as e:
            report["errors"].append(f"cutoff: {str(e)[:120]}")
            report["terminal"] = "failed"
            return report
        archive_cutoff = archive_settled_cutoff(cutoff_payload)
        if archive_cutoff is None:
            # No provider boundary, no routing. Fail closed before any DB read.
            report["errors"].append("cutoff: market_settled_ts missing or unparseable")
            report["terminal"] = "failed"
            return report
        report["archive_cutoff"] = archive_cutoff.isoformat()

        async with session_factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            params: dict = {"ticker_like": TICKER_LIKE, "lim": limit}
            if exact is not None:
                params["outcome_ids"] = exact
                sql = CANDIDATE_SQL.replace("{id_clause}", _ID_EXACT)
            else:
                params["after_id"] = int(after_id)
                params["archive_cutoff"] = archive_cutoff
                sql = CANDIDATE_SQL.replace("{id_clause}", _ID_AFTER)
            rows = (await session.execute(text(sql), params)).fetchall()
            stored: dict[int, list] = {}
            ids = [int(r.outcome_id) for r in rows]
            if ids:
                for s in (
                    await session.execute(text(STORED_INSTANTS_SQL), {"ids": ids})
                ).fetchall():
                    stored.setdefault(int(s.outcome_id), []).append(s.captured_at)
        report["candidates"] = len(rows)
        if exact is not None:
            report["ids_not_candidates"] = sorted(set(exact) - set(ids))

        listings: dict[str, _Listing] = {}
        last_done = int(after_id)
        stopped = None
        for row in rows:
            oid = int(row.outcome_id)
            ticker = row.ticker
            event_ticker = row.event_ticker
            plan = OutcomePlan(outcome_id=oid, ticker=ticker, route="unknown")
            listing = listings.setdefault(event_ticker, _Listing())
            stage = "listing"
            windows: list = []
            try:
                market = await _find_listed(
                    _get, service, listing, event_ticker, ticker
                )
                if market is None:
                    # Reached only on an EXHAUSTED listing: every page was read.
                    plan.refusal = (
                        "archive_listing_empty"
                        if not listing.markets
                        else "absent_from_archive_listing"
                    )
                else:
                    plan.refusal = identity_refusal(ticker, event_ticker, market)
                if plan.refusal is None:
                    settled_at = parse_instant(market.get("settlement_ts"))
                    plan.settled_at = settled_at.isoformat()
                    plan.route = route_market(settled_at, archive_cutoff)
                    if plan.route != ROUTE_ARCHIVE:
                        plan.refusal = f"route_{plan.route}"
                if plan.refusal is None:
                    event = (
                        SimpleNamespace(
                            commence_time=row.commence_time,
                            commence_time_source=row.commence_time_source,
                            created_at=row.created_at,
                            completed_at=row.completed_at,
                        )
                        if row.has_event
                        else None
                    )
                    cutoff, cutoff_refusal = forecast_cutoff(event, settled_at)
                    plan.forecast_cutoff = cutoff.isoformat() if cutoff else None
                    plan.cutoff_refusal = cutoff_refusal
                    open_time = parse_instant(market.get("open_time"))
                    period = choose_period(open_time, settled_at)
                    windows, opening_gap = request_windows(
                        open_time, settled_at, period
                    )
                    plan.period_minutes = period
                    plan.windows_requested = len(windows)
                    if opening_gap is not None:
                        plan.owed_windows.append(opening_gap)
                    if len(windows) > MAX_REQUESTS:
                        # No run could ever read it whole: owed by name, never sampled.
                        plan.refusal = "history_exceeds_request_cap"
                        plan.coverage = COVERAGE_INCOMPLETE
                        plan.owed_windows.extend(owed_window(w) for w in windows)
                        report["owed_ids"].append(oid)
                    else:
                        stage = "candles"
                        candles: list = []
                        for window in windows:
                            batch = await _get(
                                lambda w=window: service.get_historical_market_candlesticks_raw(
                                    ticker,
                                    period_interval=w.period_minutes,
                                    start_ts=w.start_ts,
                                    end_ts=w.end_ts,
                                )
                            )
                            plan.windows_read += 1
                            if not all(candle_is_wellformed(c) for c in batch):
                                plan.owed_windows.append(
                                    owed_window(window, OWED_MALFORMED_CANDLES)
                                )
                            candles.extend(batch)
                        points, counts = classify_candles(
                            outcome_id=oid,
                            ticker=ticker,
                            candles=candles,
                            period_minutes=period,
                            settled_at=settled_at,
                            cutoff=cutoff,
                            cutoff_refusal=cutoff_refusal,
                            stored_instants=stored.get(oid, ()),
                        )
                        plan.points = points
                        plan.counts = {**counts, "candles_returned": len(candles)}
                        plan.coverage = (
                            COVERAGE_INCOMPLETE
                            if plan.owed_windows
                            else COVERAGE_COMPLETE
                        )
                        if not candles:
                            plan.refusal = "archive_candles_empty"
            except (_RateLimited, _BudgetSpent) as e:
                # The cursor stays BEFORE this outcome; it is asked first next run.
                # Nothing it half-read becomes a plan, an absence or a coverage claim.
                stopped = "rate_limited" if isinstance(e, _RateLimited) else "partial"
                if isinstance(e, _RateLimited):
                    report["stopped_on_cooldown_s"] = e.wait
                report["held_outcome"] = _held(
                    oid, ticker, stage, listing, plan, windows
                )
                break
            except Exception as e:  # one bad outcome never wipes the pass (gotcha #42)
                report["errors"].append(f"{ticker}: {str(e)[:120]}")
                report["owed_ids"].append(oid)
                last_done = max(last_done, oid)
                continue
            if plan.coverage == COVERAGE_INCOMPLETE:
                report["incomplete_ids"].append(oid)
            report["plans"].append(plan)
            last_done = max(last_done, oid)
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            await close()

    points_all = [p for plan in report["plans"] for p in plan.points]
    totals: dict = {}
    for plan in report["plans"]:
        totals[f"refusal:{plan.refusal}"] = totals.get(f"refusal:{plan.refusal}", 0) + 1
        totals[f"coverage:{plan.coverage}"] = (
            totals.get(f"coverage:{plan.coverage}", 0) + 1
        )
        for key, value in plan.counts.items():
            totals[key] = totals.get(key, 0) + value
    report["totals"] = totals
    report["planned"] = len(report["plans"])
    report["importable_points"] = len(importable(points_all))
    report["plan_digest"] = plan_digest(points_all)
    report["plans"] = [
        {**asdict(plan), "points": [asdict(p) for p in plan.points]}
        for plan in report["plans"]
    ]
    if exact is None:
        report["next_after_id"] = last_done
        report["walk_ended"] = stopped is None and len(rows) < limit
    if stopped:
        report["terminal"] = stopped
    elif report["owed_ids"] or report["incomplete_ids"]:
        report["terminal"] = "partial"
    else:
        report["terminal"] = "complete"
    return report


def _held(
    oid: int,
    ticker: str,
    stage: str,
    listing: _Listing,
    plan: OutcomePlan,
    windows: Sequence[Any],
) -> dict:
    """Where a stopped run left the outcome it could not finish. Plan vocabulary only."""
    held: dict = {"outcome_id": oid, "ticker": ticker, "stage": stage}
    if stage == "listing":
        held.update(
            listing_pages_read=listing.pages,
            listing_cursor=listing.cursor,
            listing_exhausted=listing.exhausted,
        )
    else:
        held.update(
            period_minutes=plan.period_minutes,
            windows_requested=plan.windows_requested,
            windows_read=plan.windows_read,
            # The unread windows at the SAME width: a rerun asks these, never daily.
            owed_windows=list(plan.owed_windows)
            + [owed_window(w) for w in windows[plan.windows_read :]],
        )
    return held


async def _find_listed(
    _get, service, listing: _Listing, event_ticker: str, ticker: str
) -> Optional[dict]:
    """The listed row for ``ticker``; ``None`` ONLY once the listing is exhausted.

    Pages are read lazily and shared by sibling outcomes. An empty page that
    carries a cursor is not the end. A budget stop or a 429 propagates with the
    cursor kept, so truncated evidence never reads as absence. A listing that
    failed (malformed, 5xx, a repeated cursor) keeps failing for its siblings
    this run instead of being re-asked or read as empty.
    """
    while ticker not in listing.markets and not listing.exhausted:
        if listing.error is not None:
            raise _ListingUnreadable(listing.error)
        cursor = listing.cursor
        try:
            markets, next_cursor = await _get(
                lambda c=cursor: service.get_historical_markets(
                    event_ticker=event_ticker, limit=LISTING_PAGE_LIMIT, cursor=c
                )
            )
        except (_BudgetSpent, _RateLimited):
            raise
        except Exception as e:
            listing.error = f"listing: {str(e)[:120]}"
            raise
        listing.pages += 1
        for market in markets:
            listing.markets.setdefault(market["ticker"], market)
        if not next_cursor:
            listing.cursor = None
            listing.exhausted = True
        elif next_cursor in listing.seen_cursors or next_cursor == cursor:
            listing.error = (
                "listing: malformed_response:historical_markets:cursor_repeated"
            )
            raise _ListingUnreadable(listing.error)
        else:
            listing.seen_cursors.add(next_cursor)
            listing.cursor = next_cursor
    return listing.markets.get(ticker)
