"""#683 archive recovery: a bounded, read-only, exact-ID, resumable DRY-RUN planner.

PILLAR: TRUTH. SHIP: settled Kalshi questions that have no price history get
back their real pre-resolution probability timeline, and archive provenance stays
separate from live capture.

This module READS. Keyset discovery selects stored Kalshi outcomes that have
zero snapshots (the #683 cohort); exact ids are planned whatever their live
coverage, because archive evidence between and after live observations is
recoverable too. It asks Kalshi's historical tier about each one by its exact
stored ticker and returns the plan :mod:`app.utils.kalshi_archive_history`
decides. It writes nothing to the database, Redis or the scheduler. Entry
point: ``backend/scripts/kalshi_archive_recovery_dry_run.py``.

WHERE A PLAN GOES. Goal Root chose a separate archive store (option b,
``ROOT-STORAGE-DECISION.md``): ``futures_odds_snapshots`` has no provenance
column beyond ``bookmaker`` and no unique key, and every calibration phase reads
it without a bookmaker filter, so a ``reader_only`` archive row written there
WOULD reach the curve. The store is ``kalshi_archive_*`` (migration
``kalshi_archive_store_683``). Its only writer is the attended import,
:mod:`app.services.kalshi_archive_apply`, which takes this module's report,
re-derives every point from the response bytes the report carries, and refuses
any plan whose digest the operator did not type. "Already stored" here means
already in that store at the same period and interval end.

A RUN THAT STOPS MID-OUTCOME is resumable without replay. Its report carries a
sealed ``continuation``: the listing pages already read (markets and cursor), or
the candle windows already read WITH their exact response text. The next run,
under its own request budget, re-verifies those bytes, never asks for them
again, and reads only what is still owed.

BOUNDS, all enforced here and none of them a guess at Kalshi's rate budget:
at most :data:`MAX_OUTCOMES` outcomes and :data:`MAX_REQUESTS` GETs per run,
at least :data:`MIN_PACE_SECONDS` between GETs, and a wall-clock deadline. It
also honours the shared Kalshi cooldown that the trade rail records
(``_TRADE_BACKFILL_COOLDOWN_KEY``). It reads that key and never writes it. A 429
is waited out once, but only when ``Retry-After`` fits
``_TRADE_429_MAX_WAIT_S`` and the deadline. Otherwise the run stops, with the
cursor held BEFORE the refused outcome. A 429 is never recorded as "no data".
The deadline is re-checked after every pacing or 429 sleep, before the next GET.

AN ATTENDED RUN (``backend/scripts/kalshi_archive_recovery_dry_run.py``) adds
the rail's operational bounds (:mod:`app.services.kalshi_archive_bounds`):
``stop_on_first_429`` sends no further request after any 429, whatever its
``Retry-After`` (0 included), and refuses to start when the shared cooldown
cannot be read; ``byte_budget`` streams every response and stops the run once
one response or the run's total passes its cap; ``hard_deadline_seconds`` makes
the deadline inclusive of the database read, the cooldown read, cancelling an
in-flight request and closing the client. Every one of those stops is a held
stop (``budget_stop`` names it): the cursor stays before the outcome, nothing
half-read is planned, and the plan is never reported complete. The database
session carries the archive statement and lock bounds on every connection.

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
    continuation_refusal,
    forecast_cutoff,
    identity_refusal,
    importable,
    input_fingerprint,
    listed_identity,
    owed_window,
    parse_instant,
    plan_digest,
    request_windows,
    route_market,
    seal_continuation,
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
           fo.market_id AS market_id,
           fm.event_id AS event_id,
           fo.resolution_source AS resolution_source,
           fm.resolution_date AS resolution_date,
           (e.id IS NOT NULL) AS has_event,
           e.commence_time AS commence_time,
           e.commence_time_source AS commence_time_source,
           e.created_at AS created_at,
           e.completed_at AS completed_at,
           (SELECT COUNT(*) FROM futures_odds_snapshots fos
             WHERE fos.outcome_id = fo.id) AS live_snapshots
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    LEFT JOIN events e ON e.id = fm.event_id
    WHERE fm.source = 'kalshi'
      AND fo.external_id LIKE :ticker_like
      AND fm.external_id IS NOT NULL
      AND COALESCE(fo.resolution_source, '') NOT IN
          ('no_pregame_trading', 'did_not_play', 'withdrew')
      AND {id_clause}
    ORDER BY fo.id ASC
    LIMIT :lim
"""
#: Keyset discovery walks the #683 cohort itself: outcomes with ZERO live
#: snapshots. Exact ids do not require that. Archive evidence BETWEEN and AFTER
#: live observations is recoverable too (Root's storage decision), and the
#: reader resolves actual overlap, so a named outcome with sparse live capture
#: is planned and its live count is reported beside the plan.
_ID_AFTER = (
    "NOT EXISTS ("
    " SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id"
    ")"
    " AND fm.status = 'resolved'"
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

#: The archive store is checked first: before its migration is applied the
#: planner still runs and reports ``archive_store: absent``.
ARCHIVE_STORE_PRESENT_SQL = "SELECT to_regclass('public.kalshi_archive_intervals') IS NOT NULL"

#: Interval ends this outcome already holds IN THE ARCHIVE STORE. Live
#: snapshots are not duplicates of an archive interval: they are a different
#: kind of evidence, kept in their own table, and the reader resolves overlap.
STORED_INSTANTS_SQL = """
    SELECT outcome_id, period_minutes, interval_end
    FROM kalshi_archive_intervals
    WHERE outcome_id = ANY(:ids)
"""


class _RateLimited(Exception):
    def __init__(self, wait: Optional[float]):
        super().__init__(
            "429, cooldown unknown" if wait is None else f"429, cooldown {wait:.1f}s"
        )
        self.wait = wait


class _BudgetSpent(Exception):
    """The run must stop here, held. ``reason`` names the budget that ended it."""

    def __init__(self, reason: str = "budget"):
        super().__init__(reason)
        self.reason = reason


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


def _is_429(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


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
    """Every connection carries the archive statement/lock bounds (and proves it)."""
    from app.services.kalshi_archive_bounds import archive_session

    return archive_session()


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
    continuation: Optional[dict] = None,
    stop_on_first_429: bool = False,
    byte_budget: Any = None,
    hard_deadline_seconds: Optional[float] = None,
    progress: Optional[dict] = None,
) -> dict:
    """Plan, never write. Returns a JSON-serialisable report (see module doc).

    ``continuation`` is the sealed ``continuation`` block of an earlier report
    whose run stopped mid-outcome. That outcome resumes where it stopped, under
    THIS run's request budget: a held listing continues from its cursor with
    the markets it already read, and held candle windows are re-verified from
    their stored response text and never asked again. A carry that fails any
    check leaves the outcome owed with the reason; it is never silently re-read
    from the first window.

    ``stop_on_first_429``, ``byte_budget`` (an
    :class:`~app.services.kalshi_archive_bounds.ArchiveByteBudget`, applied by
    wrapping the service in ``BoundedArchiveService``) and
    ``hard_deadline_seconds`` (the inclusive end, at or after the work
    ``deadline_seconds``) are the attended-run bounds in the module doc.
    Omitted, each behaves exactly as before. ``progress`` receives the running
    report under ``"report"`` so a caller whose outer wall expires can still
    say what this run had done.
    """
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
    started = monotonic()
    deadline = started + max(float(deadline_seconds), 0.0)
    # The inclusive end: cancel and close must finish by then. ``None`` keeps
    # the old unbounded collection of a cancelled request and of ``close()``.
    hard_deadline = (
        None
        if hard_deadline_seconds is None
        else max(started + float(hard_deadline_seconds), deadline)
    )

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
        "archive_store": None,
        "continuation": None,
        "continuation_in": None,
        "budget_stop": None,
        "stop_on_first_429": bool(stop_on_first_429),
    }
    if byte_budget is not None:
        report["response_bytes"] = byte_budget.as_report()
    if progress is not None:
        progress["report"] = report
    if continuation is not None:
        report["continuation_in"] = {
            "outcome_id": (continuation or {}).get("outcome_id")
            if isinstance(continuation, dict)
            else None,
            "status": "not_reached",
        }
    if exact is None:
        report["selector_limits"] = list(KEYSET_SELECTOR_LIMITS)

    def _bump_progress(phase: str) -> None:
        if progress is not None:
            progress["phase"] = phase

    async def _collect_cancelled(task: "asyncio.Future", phase: str) -> None:
        """Wait for a cancelled task to unwind: unbounded (legacy) or to the hard end."""
        if hard_deadline is None:
            await asyncio.gather(task, return_exceptions=True)
            return
        done, _ = await asyncio.wait(
            {task}, timeout=max(hard_deadline - monotonic(), 0.0)
        )
        if task not in done:
            report.setdefault("cancel_unacknowledged", []).append(phase)
        elif not task.cancelled():
            task.exception()

    async def _within_deadline(call: Callable[[], Awaitable[Any]], phase: str = "request") -> Any:
        """Await one step for at most the time left; on expiry cancel it, stop held.

        ``asyncio.wait`` (not ``wait_for``) so only OUR deadline reads as a budget
        stop. A timeout raised by the call itself stays an ordinary owed error.
        """
        task = asyncio.ensure_future(call())
        done, _ = await asyncio.wait({task}, timeout=max(deadline - monotonic(), 0.0))
        if task in done:
            return task.result()
        task.cancel()
        # Collect the cancelled step (its outcome is not evidence) without
        # swallowing a cancellation of the planner itself.
        await _collect_cancelled(task, phase)
        raise _BudgetSpent("deadline")

    _bump_progress("cooldown_read")
    if hard_deadline is None:
        cooldown_left = cooldown_reader()
    else:
        try:
            cooldown_left = await _within_deadline(
                lambda: asyncio.to_thread(cooldown_reader), "cooldown_read"
            )
        except _BudgetSpent:
            cooldown_left = None
    report["shared_cooldown_s"] = (
        "unreadable" if cooldown_left is None else round(max(cooldown_left, 0.0), 1)
    )
    if cooldown_left is not None and cooldown_left > 0:
        report["terminal"] = "cooldown"
        return report
    if cooldown_left is None and stop_on_first_429:
        # Strict: an unknown shared cooldown is not permission to ask.
        report["terminal"] = "cooldown_unknown"
        return report

    state = {"sent": 0}

    def _spent_reason() -> Optional[str]:
        if state["sent"] >= max_requests:
            return "requests"
        if monotonic() >= deadline:
            return "deadline"
        return None

    async def _get(call: Callable[[], Awaitable[Any]]) -> Any:
        from app.services.kalshi_archive_bounds import ArchiveBudgetExceeded

        for attempt in range(2):
            if _spent_reason():
                raise _BudgetSpent(_spent_reason())
            if state["sent"]:
                await sleep(pace_seconds)
                # The pace (and a 429 wait before it) spends wall time: re-check,
                # so no GET leaves after the run's stated deadline.
                if _spent_reason():
                    raise _BudgetSpent(_spent_reason())
            state["sent"] += 1
            report["requests_sent"] = state["sent"]
            try:
                return await _within_deadline(call)
            except ArchiveBudgetExceeded as e:
                # A byte cap is a budget stop, never an error that reads as a
                # 429 (its message may well contain the digits "429").
                raise _BudgetSpent(e.reason) from e
            except _BudgetSpent:
                raise
            except Exception as e:
                if stop_on_first_429:
                    if _is_429(e):
                        try:
                            wait = rate_limit_wait(e)
                        except Exception:  # unknown policy: stop, honestly
                            wait = None
                        raise _RateLimited(wait) from e
                    wait = rate_limit_wait(e)
                    if wait is None:
                        raise
                    raise _RateLimited(wait) from e
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
    if byte_budget is not None:
        from app.services.kalshi_archive_bounds import BoundedArchiveService

        service = BoundedArchiveService(service, byte_budget)

    def _stop(e: BaseException) -> str:
        if isinstance(e, _RateLimited):
            report["stopped_on_cooldown_s"] = (
                "unknown" if e.wait is None else e.wait
            )
            return "rate_limited"
        report["budget_stop"] = getattr(e, "reason", "budget")
        return "partial"

    try:
        _bump_progress("cutoff")
        try:
            cutoff_payload = await _get(service.get_historical_cutoff)
        except (_BudgetSpent, _RateLimited) as e:
            report["terminal"] = _stop(e)
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

        async def _read_candidates():
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
                stored: dict[int, dict[int, list]] = {}
                ids = [int(r.outcome_id) for r in rows]
                present = bool(
                    (await session.execute(text(ARCHIVE_STORE_PRESENT_SQL))).scalar()
                )
                if ids and present:
                    for s in (
                        await session.execute(text(STORED_INSTANTS_SQL), {"ids": ids})
                    ).fetchall():
                        stored.setdefault(int(s.outcome_id), {}).setdefault(
                            int(s.period_minutes), []
                        ).append(s.interval_end)
            return rows, stored, ids, present

        _bump_progress("candidate_read")
        if hard_deadline is None:
            rows, stored, ids, present = await _read_candidates()
        else:
            # Inclusive deadline: the read is cancelled at the deadline like a
            # GET, and nothing is planned or advanced from a read that never ended.
            try:
                rows, stored, ids, present = await _within_deadline(
                    _read_candidates, "candidate_read"
                )
            except _BudgetSpent as e:
                report["terminal"] = _stop(e)
                return report
        report["archive_store"] = "present" if present else "absent"
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
            plan = OutcomePlan(
                outcome_id=oid,
                ticker=ticker,
                route="unknown",
                event_ticker=event_ticker,
                input_fingerprint=input_fingerprint(row),
                live_snapshots=int(getattr(row, "live_snapshots", 0) or 0),
            )
            carry = None
            if isinstance(continuation, dict) and continuation.get("outcome_id") == oid:
                why = continuation_refusal(
                    continuation, outcome_id=oid, ticker=ticker, event_ticker=event_ticker
                )
                if why is None and continuation.get("stage") == "candles":
                    for entry in continuation["read_windows"]:
                        try:
                            _payload_from_entry(ticker, entry)
                        except Exception as e:  # the carried bytes do not verify
                            why = f"carry_raw:{getattr(e, 'reason', type(e).__name__)}"
                            break
                report["continuation_in"] = {
                    "outcome_id": oid,
                    "status": "refused" if why else "resumed",
                    "reason": why,
                    "stage": continuation.get("stage"),
                }
                if why:
                    report["errors"].append(f"{ticker}: continuation_refused:{why}")
                    report["owed_ids"].append(oid)
                    last_done = max(last_done, oid)
                    continue
                carry = continuation
                if carry["stage"] == "listing":
                    listings[event_ticker] = _Listing(
                        markets=dict(carry["listing_markets"]),
                        cursor=carry["listing_cursor"],
                        pages=int(carry.get("listing_pages_read") or 0),
                        seen_cursors=set(carry.get("seen_cursors") or ()),
                    )
                else:
                    listings.setdefault(event_ticker, _Listing()).markets[ticker] = carry[
                        "market"
                    ]
            listing = listings.setdefault(event_ticker, _Listing())
            _bump_progress(f"outcome:{oid}")
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
                    plan.market = listed_identity(market)
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
                        lineage: list = []

                        def _take(window, payload, entry):
                            if payload.echoed_ticker != ticker:
                                # Candles for another market are never filed
                                # under this one, whoever built the payload.
                                from app.services.kalshi_api import (
                                    KalshiArchiveResponseMalformed,
                                )

                                raise KalshiArchiveResponseMalformed(
                                    "historical_candlesticks", "ticker_mismatch"
                                )
                            plan.windows.append(entry)
                            plan.windows_read += 1
                            if not all(candle_is_wellformed(c) for c in payload.candles):
                                plan.owed_windows.append(
                                    owed_window(window, OWED_MALFORMED_CANDLES)
                                )
                            candles.extend(payload.candles)
                            lineage.extend([payload.raw_sha256] * len(payload.candles))

                        resumed = (carry or {}).get("read_windows") or []
                        for window, entry in zip(windows, resumed):
                            # Re-verified from its own bytes, never asked again.
                            _take(
                                window,
                                _payload_from_entry(ticker, entry),
                                dict(entry),
                            )
                        if resumed:
                            report["continuation_in"]["windows_reused"] = len(resumed)
                        for window in windows[len(resumed) :]:
                            payload = await _get(
                                lambda w=window: service.get_historical_market_candlesticks_payload(
                                    ticker,
                                    period_interval=w.period_minutes,
                                    start_ts=w.start_ts,
                                    end_ts=w.end_ts,
                                )
                            )
                            _take(window, payload, _window_entry(window, payload))
                        points, counts = classify_candles(
                            outcome_id=oid,
                            ticker=ticker,
                            candles=candles,
                            period_minutes=period,
                            settled_at=settled_at,
                            cutoff=cutoff,
                            cutoff_refusal=cutoff_refusal,
                            stored_instants=stored.get(oid, {}).get(period, ()),
                            candle_lineage=lineage,
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
                stopped = _stop(e)
                report["held_outcome"] = _held(
                    oid, ticker, stage, listing, plan, windows
                )
                report["continuation"] = _carry(
                    oid, ticker, event_ticker, stage, listing, plan
                )
                report["held_outcome"]["continuable"] = (
                    report["continuation"] is not None
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
        _bump_progress("close")
        close = getattr(service, "close", None)
        if close is not None:
            if hard_deadline is None:
                await close()
            else:
                task = asyncio.ensure_future(close())
                done, _ = await asyncio.wait(
                    {task}, timeout=max(hard_deadline - monotonic(), 0.0)
                )
                report["client_close"] = "acknowledged" if task in done else "unacknowledged"
                if task in done and not task.cancelled() and task.exception() is not None:
                    report["client_close"] = f"failed:{type(task.exception()).__name__}"
                if task not in done:
                    task.cancel()

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
    if byte_budget is not None:
        report["response_bytes"] = byte_budget.as_report()
    if stopped:
        report["terminal"] = stopped
    elif report["owed_ids"] or report["incomplete_ids"]:
        report["terminal"] = "partial"
    else:
        report["terminal"] = "complete"
    return report


def _window_entry(window: Any, payload: Any) -> dict:
    """What a read window leaves behind: bounds, lineage and its exact bytes."""
    return {
        **asdict(window),
        "echoed_ticker": payload.echoed_ticker,
        "raw_sha256": payload.raw_sha256,
        "retrieved_at": payload.retrieved_at,
        "candles_returned": len(payload.candles),
        "raw_body": payload.raw_body,
    }


def _payload_from_entry(ticker: str, entry: dict):
    """A stored window entry back to a verified payload, or raise malformed."""
    from app.services.kalshi_api import KalshiArchiveCandlePayload

    return KalshiArchiveCandlePayload.from_raw(
        requested_ticker=ticker,
        raw_body=entry.get("raw_body") or "",
        raw_sha256=entry.get("raw_sha256") or "",
        retrieved_at=entry.get("retrieved_at") or "",
    )


def _carry(
    oid: int,
    ticker: str,
    event_ticker: str,
    stage: str,
    listing: _Listing,
    plan: OutcomePlan,
) -> Optional[dict]:
    """The sealed input the next run resumes from, or ``None`` if nothing was read.

    A carry holds only verified progress: the listing pages already read (with
    the markets they named and the cursor after them), or the candle windows
    already read with their exact response text. Nothing unread is carried, so
    the next run asks only for what is still owed, under its own budget.
    """
    base = {"outcome_id": oid, "ticker": ticker, "event_ticker": event_ticker}
    if stage == "listing":
        if not listing.cursor or listing.exhausted or listing.error:
            return None
        return seal_continuation(
            {
                **base,
                "stage": "listing",
                "listing_markets": {
                    t: listed_identity(m) for t, m in listing.markets.items()
                },
                "listing_cursor": listing.cursor,
                "listing_pages_read": listing.pages,
                "seen_cursors": sorted(listing.seen_cursors),
            }
        )
    if not plan.windows or plan.market is None:
        return None
    return seal_continuation(
        {
            **base,
            "stage": "candles",
            "market": plan.market,
            "period_minutes": plan.period_minutes,
            "read_windows": list(plan.windows),
        }
    )


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
