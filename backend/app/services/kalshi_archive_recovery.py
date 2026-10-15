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
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Optional, Sequence

from sqlalchemy import text

from app.utils.kalshi_archive_history import (
    ROUTE_ARCHIVE,
    OutcomePlan,
    archive_settled_cutoff,
    choose_period,
    classify_candles,
    forecast_cutoff,
    identity_refusal,
    importable,
    parse_instant,
    plan_digest,
    request_window,
    route_market,
)

logger = logging.getLogger(__name__)

#: Hard ceilings. The caller may ask for less and is clamped to these if it asks for more.
MAX_OUTCOMES = 200
MAX_REQUESTS = 400
MIN_PACE_SECONDS = 0.5
#: Listing pages read per event ticker before giving up on finding a market.
MAX_LISTING_PAGES = 3
LISTING_PAGE_LIMIT = 200
#: Stored outcome tickers this arm will ask about: the exact ``KX…-…-…`` shape the
#: trade rail already selects on. Passed as a bind, never inlined (gotcha #45).
TICKER_LIKE = "KX%-%-%"

#: Zero-snapshot resolved Kalshi outcomes whose BACKSTOP date already precedes
#: the archive cutoff (so the real settlement certainly does), or that have no
#: date at all (the listing then answers). ``{id_clause}`` is one of two fixed
#: strings, never caller text.
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
      AND fm.status = 'resolved'
      AND fo.external_id LIKE :ticker_like
      AND fm.external_id IS NOT NULL
      AND COALESCE(fo.resolution_source, '') NOT IN
          ('no_pregame_trading', 'did_not_play', 'withdrew')
      AND NOT EXISTS (
          SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
      )
      AND (fm.resolution_date IS NULL OR fm.resolution_date < :archive_cutoff)
      AND {id_clause}
    ORDER BY fo.id ASC
    LIMIT :lim
"""
_ID_AFTER = "fo.id > :after_id"
_ID_EXACT = "fo.id = ANY(:outcome_ids)"

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
    max_wait = _default_max_wait() if max_wait_seconds is None else max_wait_seconds
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
        "errors": [],
        "plans": [],
        "totals": {},
        "importable_points": 0,
        "plan_digest": None,
        "next_after_id": None if exact is not None else int(after_id),
        "terminal": None,
    }

    cooldown_left = cooldown_reader()
    report["shared_cooldown_s"] = (
        "unreadable" if cooldown_left is None else round(max(cooldown_left, 0.0), 1)
    )
    if cooldown_left is not None and cooldown_left > 0:
        report["terminal"] = "cooldown"
        return report

    state = {"sent": 0}

    async def _get(call: Callable[[], Awaitable[Any]]) -> Any:
        for attempt in range(2):
            if state["sent"] >= max_requests or monotonic() >= deadline:
                raise _BudgetSpent()
            if state["sent"]:
                await sleep(pace_seconds)
            state["sent"] += 1
            report["requests_sent"] = state["sent"]
            try:
                return await call()
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
            params = {
                "ticker_like": TICKER_LIKE,
                "archive_cutoff": archive_cutoff,
                "lim": limit,
            }
            if exact is not None:
                params["outcome_ids"] = exact
                sql = CANDIDATE_SQL.replace("{id_clause}", _ID_EXACT)
            else:
                params["after_id"] = int(after_id)
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

        listings: dict[str, Optional[dict]] = {}
        last_done = int(after_id)
        stopped = None
        for row in rows:
            oid = int(row.outcome_id)
            ticker = row.ticker
            event_ticker = row.event_ticker
            plan = OutcomePlan(outcome_id=oid, ticker=ticker, route="unknown")
            try:
                if event_ticker not in listings:
                    listings[event_ticker] = await _read_listing(
                        _get, service, event_ticker
                    )
                listed = listings[event_ticker]
                if listed is None:
                    plan.refusal = "archive_listing_empty"
                elif ticker not in listed:
                    plan.refusal = "absent_from_archive_listing"
                else:
                    plan.refusal = identity_refusal(
                        ticker, event_ticker, listed[ticker]
                    )
                if plan.refusal is None:
                    market = listed[ticker]
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
                    start_ts, end_ts = request_window(open_time, settled_at, period)
                    plan.period_minutes = period
                    candles = await _get(
                        lambda: service.get_historical_market_candlesticks_raw(
                            ticker,
                            period_interval=period,
                            start_ts=start_ts,
                            end_ts=end_ts,
                        )
                    )
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
                    if not candles:
                        plan.refusal = "archive_candles_empty"
            except _RateLimited as e:
                # The cursor stays BEFORE this outcome; it is asked first next run.
                stopped = "rate_limited"
                report["stopped_on_cooldown_s"] = e.wait
                break
            except _BudgetSpent:
                stopped = "partial"
                break
            except Exception as e:  # one bad outcome never wipes the pass (gotcha #42)
                report["errors"].append(f"{ticker}: {str(e)[:120]}")
                report["owed_ids"].append(oid)
                last_done = max(last_done, oid)
                continue
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
    elif report["owed_ids"]:
        report["terminal"] = "partial"
    else:
        report["terminal"] = "complete"
    return report


async def _read_listing(_get, service, event_ticker: str) -> Optional[dict]:
    """Every archived market of one event, keyed by exact ticker; ``None`` if empty."""
    found: dict = {}
    cursor: Optional[str] = None
    for _ in range(MAX_LISTING_PAGES):
        markets, cursor = await _get(
            lambda c=cursor: service.get_historical_markets(
                event_ticker=event_ticker, limit=LISTING_PAGE_LIMIT, cursor=c
            )
        )
        for market in markets:
            if isinstance(market, dict) and market.get("ticker"):
                found.setdefault(market["ticker"], market)
        if not cursor:
            break
    return found or None
