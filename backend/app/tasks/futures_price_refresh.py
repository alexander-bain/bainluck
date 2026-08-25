"""#2199 — refresh prices for high-value open futures markets that the
discovery polls structurally cannot reach.

THE DEFECT THIS EXISTS FOR
--------------------------
Price capture for an *already-known* futures market was, until this module, a
side effect of a *discovery* scan. Both discovery scans are bounded, and both
orderings put already-known markets last:

* **Polymarket** (`_poll_polymarket_markets`). Gamma capped offset pagination at
  2000 in July 2026, so #219E flipped the scan to ``order=startDate&ascending=
  false`` — newest-listed first — to stop the *new*-market starvation. Measured
  2026-08-25: the deepest reachable page (offset 1900-1999) had an oldest
  ``startDate`` of **the same day**, and 73/100 events on page 0 were crypto
  up/down five-minute binaries the poll then discards. The entire reachable
  universe is roughly the last ten hours of listings. The 2026 Men's US Open
  Winner field has ``startDate = 2026-01-02`` — seven months deep in a tail the
  poll can never reach. #219E did not fix the starvation, it mirrored it:
  oldest-first starved new markets, newest-first starves old-but-live ones.
  Gotcha #41: a bounded sweep needs BOTH bounds.

* **Kalshi** (`_poll_kalshi_markets`). ``_partition_new_events_first`` defers
  every already-known event behind every new one, and the 480s processing
  deadline truncates the run long before the tail. The comment justifying that
  ordering says deferring existing rows is safe because "kalshi_ws + live poll
  keep them fresh anyway". That premise is false for futures:
  ``poll_live_prediction_markets`` is scoped to markets *linked to live events*
  and an outright championship field has no ``event_id``.

Measured blast radius (production, 2026-08-25): of the **907** tier-1 `open`
markets above a $10K volume floor with a future resolution date, **900** had
received no price snapshot in six hours. Not a tennis problem — the Super Bowl
LXI, 2028 presidential, MLB / NBA / UCL / Premier League championship and March
Madness fields were all dark.

WHAT THIS TASK IS, AND IS NOT
-----------------------------
It is a **price refresh**, and nothing else. It selects markets that already
exist in our DB, fetches those specific markets by id, and writes
``futures_outcomes`` price columns plus a ``futures_odds_snapshots`` row.

It deliberately does NOT create markets, create outcomes, categorise, re-tier,
group, or touch ``event_id``. Discovery stays the polls' job. This separation is
the actual fix: refresh coverage no longer depends on a discovery ordering, so
the two can never starve each other again.

STARVATION GUARDS (gotcha #41 — an ordering needs both bounds)
--------------------------------------------------------------
* **Value floor and liveness floor**, not a bare "oldest first": tier 1, volume
  at or above :data:`HIGH_VALUE_VOLUME_FLOOR`, ``status='open'``, and a
  resolution date in the future. Gotcha #33 (settled Kalshi markets keep
  ``status='open'``) means ``status`` alone is not a liveness test; the
  resolution-date bound is what keeps the dead out of the queue.
* **Ordered by value, not by staleness.** Oldest-capture-first looks right and
  is a trap here: a market that can never be priced (a stale-settled book
  returning no bid, ask or trade) has a NULL last-capture forever, so it would
  hold the head of the queue permanently and starve everything behind it. Volume
  DESC has no such fixed point.
* **Per-market attempt markers** in Redis with a TTL equal to the staleness
  window, so one run cannot re-attempt what the previous run just tried and the
  tail rotates into view. An *attempt* is marked, not a success — otherwise the
  unpriceable market is back at the front on the very next run.

VERDICT
-------
Enrolled in :data:`app.utils.task_verdict.ENFORCED_TASKS` from birth, per #1884.
The failure this task must never report as green is precisely the one it was
built to end: a run that fetched markets, wrote no snapshots, and returned.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

#: Only markets at or above this traded volume are refreshed. The floor is what
#: makes the sweep bounded; the guard in ``routes/admin_futures_freshness.py``
#: asserts the invariant over exactly this same set, so fix and guard cannot
#: disagree about what they cover.
HIGH_VALUE_VOLUME_FLOOR = 10_000

#: A high-value open market older than this is stale. Matches the 6h
#: ``LIVE_PRICE_STALE`` contract that ``utils/tournament_register.py`` already
#: enforces at the render boundary (UX-P130), so the producer and the renderer
#: use one definition of stale rather than two.
STALE_AFTER_HOURS = 6

#: Markets refreshed per run. 900 was the whole standing backlog when this
#: shipped; the budget exists so a bad day cannot turn one run into a wall-clock
#: overrun, not because the full set is unaffordable.
DEFAULT_MARKET_BUDGET = 500

#: Polymarket ids per Gamma ``/events?id=..&id=..`` request. Verified against the
#: live API 2026-08-25: repeated ``id`` params return the full nested markets
#: payload for each event.
POLYMARKET_ID_BATCH = 20

#: Wall budget, well under the task's 540s soft limit. Bounds the LOOP; each
#: individual HTTP call is separately bounded by the service clients' timeouts.
_TIME_BUDGET_S = 420.0

_ATTEMPT_KEY_PREFIX = "bainluck:futures_price_refresh:attempted:"


def _attempt_key(market_id: int) -> str:
    return f"{_ATTEMPT_KEY_PREFIX}{market_id}"


# --- selection ---------------------------------------------------------------

#: ``NOT EXISTS`` with a time bound rather than ``MAX(captured_at)``: the
#: aggregate form timed out at 10s in production over the 179M-row snapshot
#: table, because it must read every snapshot for every candidate. The EXISTS
#: form rides ``idx_fos_outcome_captured`` (outcome_id, captured_at) and stops at
#: the first row inside the window.
_CANDIDATE_SQL = text(
    """
    SELECT fm.id, fm.source, fm.external_id, fm.volume
      FROM futures_markets fm
     WHERE fm.status = 'open'
       AND fm.source IN ('kalshi', 'polymarket')
       AND fm.market_tier = 1
       AND fm.volume >= :volume_floor
       AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :stale_hours)
           )
     ORDER BY fm.volume DESC
     LIMIT :scan_limit
    """
)


async def _scan_candidates(
    session, *, volume_floor: int, stale_hours: int, scan_limit: int
) -> list[dict]:
    """Stale high-value markets, most valuable first.

    Scans wider than one run's budget on purpose: the caller then drops markets
    already attempted inside the staleness window, and without the headroom a run
    whose top-N were all just attempted would do nothing while the tail stayed
    dark.
    """
    rows = (
        await session.execute(
            _CANDIDATE_SQL,
            {
                "volume_floor": volume_floor,
                "stale_hours": stale_hours,
                "scan_limit": scan_limit,
            },
        )
    ).fetchall()
    return [
        {"id": mid, "source": source, "external_id": external_id, "volume": volume}
        for mid, source, external_id, volume in rows
    ]


def _load_attempt_skips(market_ids: list[int]) -> set[int]:
    """Market ids attempted inside the current staleness window.

    Best-effort. Gotcha #39: only ever through ``get_redis_client()``, which is
    socket-timeout bounded — an unbounded sync client here would freeze the
    async task. A Redis outage degrades this to "no rotation", which is strictly
    better than not running.
    """
    if not market_ids:
        return set()
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        values = rc.mget([_attempt_key(mid) for mid in market_ids])
    except Exception:
        return set()
    return {mid for mid, val in zip(market_ids, values) if val}


def _mark_attempted(market_ids: list[int], ttl_seconds: int) -> None:
    """Record an ATTEMPT, not a success.

    A market whose book cannot be priced would otherwise return to the head of
    the queue on every single run and starve the tail behind it — the same
    fixed-point failure the volume ordering above avoids.
    """
    if not market_ids:
        return
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        pipe = rc.pipeline()
        for mid in market_ids:
            pipe.setex(_attempt_key(mid), ttl_seconds, "1")
        pipe.execute()
    except Exception:
        pass


# --- writing -----------------------------------------------------------------


async def _write_prices(
    session,
    market_id: int,
    bookmaker: str,
    priced: list[dict],
    stats: dict,
) -> int:
    """Write price columns + one snapshot per outcome. Returns snapshots written.

    ``priced`` items: ``external_id``, ``probability``, ``yes_bid``, ``yes_ask``,
    ``last_price``.

    Three refusals, each load-bearing:

    * **Never creates an outcome.** An id we do not already hold is discovery's
      job; creating one here would let a price-only path mint identity with no
      categorisation, tier or grouping. Counted as ``unknown_outcomes`` so the
      refusal is visible rather than silent.
    * **Never touches a settled outcome** (``is_winner`` set). Gotcha #21: a
      settled book stops quoting, and re-pricing it can only corrupt resolved
      state.
    * **Never writes a NULL probability.** Gotcha #19 / the Kalshi spread guard:
      "no price" is refused upstream, and a refusal must not arrive here as a
      write.
    """
    from app.models.models import FuturesOddsSnapshot, FuturesOutcome
    from app.utils.odds_math import probability_to_american
    from app.utils.price_change_stamp import price_changed_at_value
    from sqlalchemy import func, update as sa_update

    if not priced:
        return 0

    existing = {
        row[1]: row[0]
        for row in (
            await session.execute(
                text(
                    "SELECT id, external_id FROM futures_outcomes "
                    "WHERE market_id = :mid AND is_winner IS NULL"
                ),
                {"mid": market_id},
            )
        ).fetchall()
    }

    now = datetime.now(timezone.utc)
    written = 0
    for item in priced:
        prob = item.get("probability")
        if prob is None or not (0 < prob < 1):
            continue
        outcome_id = existing.get(item["external_id"])
        if outcome_id is None:
            stats["unknown_outcomes"] += 1
            continue

        american = probability_to_american(prob)
        await session.execute(
            sa_update(FuturesOutcome)
            .where(FuturesOutcome.id == outcome_id)
            .values(
                current_probability=prob,
                current_american_odds=american,
                current_yes_bid=item.get("yes_bid"),
                current_yes_ask=item.get("yes_ask"),
                last_updated=func.now(),
                # #2024: `last_updated` records that a poll RAN; this records
                # that the price MOVED. Both matter and they are not the same.
                price_changed_at=price_changed_at_value(
                    FuturesOutcome.current_probability,
                    FuturesOutcome.price_changed_at,
                    prob,
                ),
            )
        )
        await session.execute(
            pg_insert(FuturesOddsSnapshot).values(
                outcome_id=outcome_id,
                bookmaker=bookmaker,
                probability=prob,
                american_odds=american,
                yes_bid=item.get("yes_bid"),
                yes_ask=item.get("yes_ask"),
                last_price=item.get("last_price"),
                captured_at=now,
            )
        )
        written += 1

    return written


# --- source adapters ---------------------------------------------------------


async def _fetch_kalshi_prices(service, external_id: str) -> Optional[list[dict]]:
    """Prices for one Kalshi event ticker, or None when the event is gone.

    Two deliberate reuses rather than reimplementations:

    * ``service._parse_event`` for the payload. Kalshi v2 quotes prices in TWO
      formats — ``yes_bid_dollars`` as a decimal string, or legacy ``yes_bid`` as
      integer cents — and ``_parse_market`` already resolves the pair. Reading
      the raw dict here would mean re-deriving that, and a ``95`` arriving where
      ``0.95`` is expected is a coherent-looking wrong price, the worst kind.
    * ``_kalshi_yes_probability`` for the price itself — the same spread /
      one-sided-book guard the main poll applies, so this path cannot fabricate a
      price the poll would have refused.
    """
    from app.tasks.kalshi import _kalshi_yes_probability

    raw = await service.get_event(external_id, with_nested_markets=True)
    if not raw:
        return None
    event = service._parse_event(raw)
    if not event:
        return None

    priced: list[dict] = []
    for market in event.markets:
        if not market.ticker:
            continue
        prob = _kalshi_yes_probability(
            market.yes_bid, market.yes_ask, market.last_price
        )
        if prob is None:
            continue
        priced.append(
            {
                "external_id": market.ticker,
                "probability": prob,
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
                "last_price": market.last_price,
            }
        )
    return priced


async def _fetch_polymarket_prices(service, event_ids: list[str]) -> dict[str, list[dict]]:
    """Prices for a batch of Polymarket event ids, keyed by event id.

    Applies the same two field-level refusals as the ingest path:
    ``_resolve_market_probability`` (placeholder/evidence gate, gotcha #19) and
    ``field_is_incoherent`` (#1527 — a negRisk field with several near-certain
    legs is not a price at any leg, and capturing it poisons
    ``opening_probability`` permanently because opening is COALESCEd).
    """
    from app.tasks.polymarket import _resolve_market_probability
    from app.utils.winner_field_coherence import field_is_incoherent

    raw_events = await service.get_events_by_ids(event_ids)
    out: dict[str, list[dict]] = {}
    for raw in raw_events:
        event = service._parse_event(raw)
        if not event or not event.markets:
            continue
        priced: list[dict] = []
        for market in event.markets:
            prob = _resolve_market_probability(market)
            if prob is None or prob <= 0:
                continue
            priced.append(
                {
                    "external_id": market.condition_id,
                    "probability": prob,
                    "yes_bid": market.best_bid,
                    "yes_ask": market.best_ask,
                    "last_price": market.last_trade_price,
                }
            )
        if not priced:
            continue
        if field_is_incoherent(
            (p["probability"] for p in priced),
            mutually_exclusive=bool(event.neg_risk),
        ):
            logger.warning(
                "futures_price_refresh: polymarket event %s — incoherent negRisk "
                "field, refusing capture (#1527)",
                event.id,
            )
            continue
        out[str(event.id)] = priced
    return out


# --- entry point -------------------------------------------------------------


async def _refresh_stale_futures_prices(
    *,
    volume_floor: int = HIGH_VALUE_VOLUME_FLOOR,
    stale_hours: int = STALE_AFTER_HOURS,
    budget: int = DEFAULT_MARKET_BUDGET,
) -> dict:
    """Refresh prices for stale high-value open futures markets. See module docstring."""
    from app.tasks.base import get_task_session

    started = time.monotonic()
    stats: dict = {
        "task": "futures_price_refresh",
        "candidates": 0,
        "markets_attempted": 0,
        "markets_priced": 0,
        "snapshots_written": 0,
        "unknown_outcomes": 0,
        "not_found": 0,
        "unpriceable": 0,
        "errors": [],
        "by_source": {},
        "remaining_stale": None,
        "budget_hit": False,
    }

    async with get_task_session() as session:
        # Bound the longest single uninterrupted DB op rather than the loop
        # boundaries (gotcha: budget-guard-inner-op). A loop-boundary check
        # cannot interrupt a statement already blocked on a row lock held by the
        # live poller.
        await session.execute(text("SET statement_timeout = '60s'"))
        await session.execute(text("SET lock_timeout = '15s'"))

        scan = await _scan_candidates(
            session,
            volume_floor=volume_floor,
            stale_hours=stale_hours,
            scan_limit=max(budget * 3, budget + 50),
        )
        stats["candidates"] = len(scan)
        skip_ids = _load_attempt_skips([m["id"] for m in scan])
        selected = [m for m in scan if m["id"] not in skip_ids][:budget]

        if not selected:
            # Gotcha #53: an empty result is a response SHAPE, not an absence.
            # "Nothing stale" and "everything stale was just attempted" are
            # opposite states, so they get different terminals.
            stats["terminal"] = "complete" if not scan else "no_work"
            stats["reason"] = (
                "no stale high-value markets"
                if not scan
                else "every stale market was attempted inside the current window"
            )
            stats["remaining_stale"] = len(scan)
            return stats

        kalshi_markets = [m for m in selected if m["source"] == "kalshi"]
        poly_markets = [m for m in selected if m["source"] == "polymarket"]
        attempted_ids: list[int] = []

        # --- Polymarket: batched by id, so the whole backlog costs ~25 calls ---
        if poly_markets:
            from app.services.polymarket_api import PolymarketAPIService

            poly_service = PolymarketAPIService()
            try:
                by_external = {m["external_id"]: m for m in poly_markets}
                ids = list(by_external.keys())
                for i in range(0, len(ids), POLYMARKET_ID_BATCH):
                    if time.monotonic() - started > _TIME_BUDGET_S:
                        stats["budget_hit"] = True
                        break
                    chunk = ids[i : i + POLYMARKET_ID_BATCH]
                    try:
                        priced_by_event = await _fetch_polymarket_prices(
                            poly_service, chunk
                        )
                    except Exception as exc:  # one bad batch must not wipe the run
                        stats["errors"].append(f"polymarket batch {i}: {exc}")
                        continue
                    for external_id in chunk:
                        market = by_external[external_id]
                        attempted_ids.append(market["id"])
                        stats["markets_attempted"] += 1
                        priced = priced_by_event.get(external_id)
                        if priced is None:
                            stats["not_found"] += 1
                            continue
                        try:
                            written = await _write_prices(
                                session, market["id"], "polymarket", priced, stats
                            )
                            await session.commit()
                        except Exception as exc:
                            await session.rollback()
                            stats["errors"].append(f"polymarket {external_id}: {exc}")
                            continue
                        if written:
                            stats["markets_priced"] += 1
                            stats["snapshots_written"] += written
                            stats["by_source"]["polymarket"] = (
                                stats["by_source"].get("polymarket", 0) + written
                            )
                        else:
                            stats["unpriceable"] += 1
                    await asyncio.sleep(0.3)
            finally:
                await poly_service.close()

        # --- Kalshi: one call per event ticker; no batch endpoint exists ---
        if kalshi_markets:
            import os

            if not os.getenv("KALSHI_API_KEY"):
                stats["errors"].append("KALSHI_API_KEY not configured")
            else:
                from app.services.kalshi_api import KalshiAPIService

                kalshi_service = KalshiAPIService()
                for market in kalshi_markets:
                    if time.monotonic() - started > _TIME_BUDGET_S:
                        stats["budget_hit"] = True
                        break
                    attempted_ids.append(market["id"])
                    stats["markets_attempted"] += 1
                    try:
                        priced = await _fetch_kalshi_prices(
                            kalshi_service, market["external_id"]
                        )
                    except Exception as exc:
                        stats["errors"].append(f"kalshi {market['external_id']}: {exc}")
                        continue
                    if priced is None:
                        stats["not_found"] += 1
                        continue
                    try:
                        written = await _write_prices(
                            session, market["id"], "kalshi", priced, stats
                        )
                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        stats["errors"].append(f"kalshi {market['external_id']}: {exc}")
                        continue
                    if written:
                        stats["markets_priced"] += 1
                        stats["snapshots_written"] += written
                        stats["by_source"]["kalshi"] = (
                            stats["by_source"].get("kalshi", 0) + written
                        )
                    else:
                        stats["unpriceable"] += 1
                    await asyncio.sleep(0.15)

        _mark_attempted(attempted_ids, ttl_seconds=stale_hours * 3600)

        # Measure what is LEFT, so the run reports the invariant's state and not
        # just its own throughput. This is the number the guard reads.
        try:
            remaining = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM futures_markets fm
                         WHERE fm.status = 'open'
                           AND fm.source IN ('kalshi', 'polymarket')
                           AND fm.market_tier = 1
                           AND fm.volume >= :volume_floor
                           AND (fm.resolution_date IS NULL
                                OR fm.resolution_date > NOW())
                           AND NOT EXISTS (
                                 SELECT 1 FROM futures_outcomes fo
                                   JOIN futures_odds_snapshots s
                                     ON s.outcome_id = fo.id
                                  WHERE fo.market_id = fm.id
                                    AND s.captured_at
                                        > NOW() - make_interval(hours => :stale_hours)
                               )
                        """
                    ),
                    {"volume_floor": volume_floor, "stale_hours": stale_hours},
                )
            ).scalar()
            stats["remaining_stale"] = int(remaining or 0)
        except Exception as exc:
            stats["errors"].append(f"remaining_stale census: {exc}")

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    stats["terminal"] = _terminal(stats)
    return stats


def _terminal(stats: dict) -> str:
    """The honest terminal. #1884: enrolled from birth, so this is the contract.

    A run that attempted markets and wrote nothing is ``failed``, not
    ``complete`` — that is the exact false-green this task exists to end
    (gotcha #53: "it returned" is not "it worked"). A budget- or error-truncated
    run that did write is ``partial``: real work banked, coverage not proven.
    """
    if stats["markets_attempted"] == 0:
        return "no_work"
    if stats["snapshots_written"] == 0:
        return "failed"
    if stats["budget_hit"] or stats["errors"]:
        return "partial"
    return "complete"
