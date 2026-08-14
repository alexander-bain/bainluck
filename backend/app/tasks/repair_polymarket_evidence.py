"""Polymarket trading-evidence recovery — #1870 (CAL-P060).

WHAT WAS ACTUALLY WRONG
=======================

#1870 asked us to state whether the 71.4% NULL is "ordering starvation, a scope
filter, or a failing call". It is none of the three.

**The call does not exist.** ``_backfill_polymarket_volume`` in
``app/tasks/polymarket.py`` is a complete, careful, resumable backfill — with a
Redis cursor, 429 backoff, an overflow clamp and a bulk unnest write — and it
has **no caller anywhere in the repository**. No Celery task wraps it, no beat
entry schedules it, no route invokes it. Its single reference outside its own
``def`` is ``tests/test_polymarket.py::test_backfill_volume_fn_shape``, which
reads the function's SOURCE TEXT with ``inspect.getsource`` and asserts that the
strings ``"unnest"``, ``"429"`` and ``"bainluck:poly_volume_backfill"`` appear in
it. Every one of those assertions passes on a function that has never executed.
The 28.6% of rows that DO carry volume come from forward capture during polling
(``_process_event_batch``), which only ever sees markets while they are open.

Two further defects, measured 2026-08-14, which matter because they mean wiring
that function up would NOT have fixed this either:

1. **``order=volume&ascending=false`` is a LEXICOGRAPHIC sort.** Measured
   first-page volumes: ``99.99999999999999``, then ``999.96``, then ``99.996``,
   then ``9.999343``. That is the volume *string* in descending order, not the
   number. Its docstring's promise — "high-volume-first ... so the
   meaningful-volume markets are filled before the long tail" — is false: a
   $12M market sorts under ``1`` and lands near the end, and a market with
   volume ``0`` sorts dead last of all. **That is why Polymarket has exactly
   0.00% confirmed zeros**: the only rows that would produce one are the last
   rows the sweep would ever reach.

2. **``gamma/markets?offset=`` caps at 2000** (2000 → 200, 2050 → 422). So the
   sweep could address ~2,100 markets total, forever, and would never reach the
   ``wrapped`` branch that resets its cursor. Against a NULL cohort in the tens
   of thousands, the pager is not slow; it is bounded away from the answer.

Gotcha #41's family, third variant. Not newest-first, not oldest-first-without-a
-floor: **ordered by a key that does not sort, against a ceiling.** Ordering is
never the whole answer — ask what the ordering starts on, and whether it sorts.

WHAT THIS RAIL DOES INSTEAD
===========================

It does not page ``/markets`` at all, because that address is capped. It
addresses ``gamma/events/{polymarket_event_id}`` — an id we already store on
107,168 Polymarket markets — which returns every sub-market of the event with
its authoritative ``volume`` and ``conditionId``, has no offset cap, and costs
one call per event rather than one per market.

Ordering is **oldest-first WITHIN a floor** (gotcha #41 / CAL-P009's amendment).
Oldest-first alone would spend every run on the ~999 rows measured permanently
unaddressable, which sort first and can never be recovered. A floor alone would
leave the oldest recoverable rows last, which is fatal if the boundary turns out
to roll. Both bounds, or neither works.

Nothing is written on a verdict of UNADDRESSABLE or INDETERMINATE. See
``app/utils/polymarket_evidence`` for why that is the whole point.

ATTENDED ONLY: never wire this to a beat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import text

from app.utils.polymarket_evidence import (
    PM_ADDRESSABLE_FROM,
    PM_BOUNDARY_MEASURED_ON,
    PM_SWEEP_FLOOR,
    PM_UNADDRESSABLE_THROUGH,
    PMEvidence,
    build_evidence_receipt,
    classify_pm_evidence,
    volume_to_write,
)

logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"

#: Markets touched per apply call. A module constant, deliberately: the operator
#: re-invokes with the returned cursor, the operator does not raise the ceiling.
APPLY_MARKET_CAP = 60

#: Wall-clock bound for one call. Bounds the longest single uninterrupted
#: operation, not the loop boundary (the budget-guard lesson).
DEADLINE_SECONDS = 55

#: Pause between venue calls. Polymarket's Gamma limiter is real and much of
#: what past windows read as throttling was a 422 from a mis-addressed call.
VENUE_PAUSE = 0.35


# ---------------------------------------------------------------------------
# Census — read-only. Never writes; `apply` is accepted and ignored.
# ---------------------------------------------------------------------------

_BAND_SQL = f"""
    CASE
      WHEN fm.resolution_date IS NULL THEN 'no_resolution_date'
      WHEN fm.resolution_date <= DATE '{PM_UNADDRESSABLE_THROUGH.isoformat()}'
        THEN 'a_pre_boundary_dead'
      WHEN fm.resolution_date <  DATE '{PM_ADDRESSABLE_FROM.isoformat()}'
        THEN 'b_boundary_zone_unmeasured'
      WHEN fm.resolution_date <  DATE '2025-01-01' THEN 'c_2024'
      WHEN fm.resolution_date <  DATE '2026-01-01' THEN 'd_2025'
      WHEN fm.resolution_date <= CURRENT_DATE      THEN 'e_2026_to_date'
      ELSE 'f_future_dated'
    END
"""


async def census(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """The four-state census, by age band. Read-only.

    #1870's third acceptance criterion asks for "a census distinguishing the
    three states, not a rowcount". It is reported here as FOUR, because the
    probe found a state the issue could not have anticipated: a market the venue
    will not address at any URL. Folding that into "confirmed zero" is the exact
    error the fix exists to prevent, so it is not folded into anything.

    Banding is derived from ``resolution_date``. #1868 is open on that column's
    provenance for Kalshi and its finding may re-shape these bands; that is
    declared here rather than discovered later.
    """
    rows = (
        await session.execute(
            text(
                f"""
                SELECT {_BAND_SQL} AS band,
                       COUNT(*) AS n_outcomes,
                       COUNT(*) FILTER (WHERE fo.volume IS NULL)  AS n_null,
                       COUNT(*) FILTER (WHERE fo.volume = 0)      AS n_zero,
                       COUNT(*) FILTER (WHERE fo.volume > 0)      AS n_positive,
                       COUNT(*) FILTER (
                           WHERE fo.volume IS NULL
                             AND fm.market_metadata ? 'volume_evidence'
                       ) AS n_null_with_receipt,
                       COUNT(*) FILTER (
                           WHERE fm.market_metadata ? 'polymarket_event_id'
                       ) AS n_addressable_by_event
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.source = 'polymarket'
                GROUP BY 1
                ORDER BY 1
                """
            )
        )
    ).all()

    bands = [
        {
            "band": r.band,
            "n_outcomes": r.n_outcomes,
            "unfetched_null_no_receipt": r.n_null - r.n_null_with_receipt,
            "asked_but_unknowable_null_with_receipt": r.n_null_with_receipt,
            "confirmed_zero": r.n_zero,
            "traded": r.n_positive,
            "recoverable_via_event_id": r.n_addressable_by_event,
        }
        for r in rows
    ]
    total_null = sum(b["unfetched_null_no_receipt"] for b in bands)
    dead = sum(
        b["unfetched_null_no_receipt"]
        for b in bands
        if b["band"] == "a_pre_boundary_dead"
    )
    return {
        "repair": "polymarket-evidence-census",
        "wrote_anything": False,
        "measured": True,
        "boundary": {
            "unaddressable_through": PM_UNADDRESSABLE_THROUGH.isoformat(),
            "addressable_from": PM_ADDRESSABLE_FROM.isoformat(),
            "measured_on": PM_BOUNDARY_MEASURED_ON.isoformat(),
            "re_measure_with": "backend/scripts/probe_polymarket_retention.py",
            "rolls": "UNKNOWN — one observation cannot distinguish a fixed "
                     "boundary from a slow one. Re-run the probe.",
        },
        "bands": bands,
        "unfetched_total": total_null,
        "unfetched_permanently_dead": dead,
        "unfetched_recoverable": total_null - dead,
    }


# ---------------------------------------------------------------------------
# Venue reads
# ---------------------------------------------------------------------------


async def _fetch_event_volumes(
    client: httpx.AsyncClient, event_id: str
) -> Optional[dict[str, float]]:
    """conditionId -> authoritative volume, for every sub-market of an event.

    Returns None on a failed probe — NEVER an empty dict, which a caller could
    read as "the event has no markets". Gotcha #53 is a discipline about return
    types before it is one about HTTP.
    """
    try:
        r = await client.get(f"{GAMMA}/events/{event_id}", timeout=25)
    except (httpx.TimeoutException, httpx.TransportError):
        return None
    if r.status_code != 200:
        return None
    try:
        body = r.json()
    except (ValueError, json.JSONDecodeError):
        return None
    markets = body.get("markets") if isinstance(body, dict) else None
    if not isinstance(markets, list):
        return None
    out: dict[str, float] = {}
    for m in markets:
        cid = m.get("conditionId") or m.get("condition_id")
        vol = m.get("volume")
        if vol is None:
            vol = m.get("volumeNum")
        if cid is None or vol is None:
            continue
        try:
            out[str(cid)] = float(vol)
        except (TypeError, ValueError):
            continue
    return out


async def _probe_market(
    client: httpx.AsyncClient, condition_id: str
) -> tuple[Optional[int], Optional[list]]:
    """(clob existence status, parsed trades) — the two independent signals.

    Existence is fetched even when trades are available, because trades alone
    cannot tell purged from untraded. That extra call IS the fix.
    """
    status: Optional[int] = None
    try:
        r = await client.get(f"{CLOB}/markets/{condition_id}", timeout=25)
        status = r.status_code
    except (httpx.TimeoutException, httpx.TransportError):
        return None, None
    await asyncio.sleep(VENUE_PAUSE)

    if status == 404:
        # Unaddressable. Do not spend a call on trades: whatever it returns is
        # a statement about Polymarket's index, not about this market.
        return status, None

    trades: Optional[list] = None
    try:
        t = await client.get(f"{DATA}/trades?market={condition_id}&limit=500", timeout=25)
        if t.status_code == 200:
            parsed = t.json()
            trades = parsed if isinstance(parsed, list) else None
    except (httpx.TimeoutException, httpx.TransportError, ValueError):
        trades = None
    return status, trades


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int = None,
    after_date: str = None,
    after_id: int = None,
    **_ignored,
) -> dict[str, Any]:
    """Fetch trading evidence for the NULL cohort, oldest-first within the floor.

    Resumable by KEYSET (``after_date`` + ``after_id`` from ``next_cursor``),
    never by offset: this repair removes rows from its own population, so an
    offset would skip exactly as many untouched rows as the last page fixed
    (C-CERT-1852's finding, applied here at staging time rather than after a
    certification round).
    """
    started = time.monotonic()
    cap = min(int(limit or APPLY_MARKET_CAP), APPLY_MARKET_CAP)

    params: dict[str, Any] = {"floor": PM_SWEEP_FLOOR.isoformat(), "cap": cap}
    keyset = ""
    if after_date and after_id:
        keyset = "AND (fm.resolution_date, fm.id) > (CAST(:after_date AS date), :after_id)"
        params["after_date"] = after_date
        params["after_id"] = int(after_id)

    # One row per MARKET: the fetch is addressed per market, so the unit of work
    # is a market, and its outcomes are updated together.
    targets = (
        await session.execute(
            text(
                f"""
                SELECT fm.id                                   AS market_id,
                       fm.resolution_date::date                AS rd,
                       fm.market_metadata->>'polymarket_event_id' AS event_id,
                       MIN(split_part(fo.external_id, '_', 1)) AS condition_id,
                       COUNT(*)                                AS n_null_outcomes
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.source = 'polymarket'
                  AND fo.volume IS NULL
                  AND fm.resolution_date > CAST(:floor AS date)
                  AND NOT (fm.market_metadata ? 'volume_evidence')
                  {keyset}
                GROUP BY fm.id, fm.resolution_date, fm.market_metadata
                ORDER BY fm.resolution_date ASC, fm.id ASC
                LIMIT :cap
                """
            ),
            params,
        )
    ).all()

    counts = {
        "markets_examined": 0,
        "traded": 0,
        "confirmed_zero": 0,
        "unaddressable": 0,
        "indeterminate": 0,
        "outcomes_written": 0,
        "receipts_written": 0,
    }
    by_band: dict[str, dict[str, int]] = {}
    next_cursor: Optional[dict[str, Any]] = None
    stopped_before: Optional[str] = None
    event_cache: dict[str, Optional[dict[str, float]]] = {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for t in targets:
            if (time.monotonic() - started) > DEADLINE_SECONDS:
                stopped_before = f"market_id={t.market_id}"
                break

            counts["markets_examined"] += 1
            band = str(t.rd.year) if t.rd else "unknown"
            slot = by_band.setdefault(
                band,
                {"traded": 0, "confirmed_zero": 0, "unaddressable": 0, "indeterminate": 0},
            )

            gamma_volume: Optional[float] = None
            if t.event_id:
                if t.event_id not in event_cache:
                    event_cache[t.event_id] = await _fetch_event_volumes(client, t.event_id)
                    await asyncio.sleep(VENUE_PAUSE)
                vols = event_cache[t.event_id]
                if vols is not None and t.condition_id:
                    gamma_volume = vols.get(t.condition_id)

            clob_status, trades = await _probe_market(client, t.condition_id)
            await asyncio.sleep(VENUE_PAUSE)

            evidence = classify_pm_evidence(
                clob_status=clob_status, trades=trades, gamma_volume=gamma_volume
            )
            counts[evidence.value] += 1
            slot[evidence.value] += 1
            next_cursor = {"after_date": t.rd.isoformat(), "after_id": t.market_id}

            if not apply:
                continue

            value = volume_to_write(evidence, gamma_volume)
            receipt = build_evidence_receipt(
                evidence,
                n_trades=len(trades) if trades is not None else None,
                gamma_volume=gamma_volume,
                fetched_at=datetime.now(timezone.utc),
            )

            if value is not None:
                # Core UPDATE, never ORM attribute assignment (gotcha #4/#5).
                # Guarded to volume IS NULL so a concurrent forward capture that
                # already wrote a real figure is never overwritten by ours.
                r = await session.execute(
                    text(
                        """
                        UPDATE futures_outcomes
                        SET volume = :vol, last_updated = NOW()
                        WHERE market_id = :mid AND volume IS NULL
                        """
                    ),
                    {"vol": value, "mid": t.market_id},
                )
                counts["outcomes_written"] += r.rowcount

            # The receipt is written for EVERY completed probe except a failed
            # one — including UNADDRESSABLE, which is the whole point: it is
            # what makes that NULL readable as permanent rather than pending.
            if evidence is not PMEvidence.INDETERMINATE:
                # CAST(:p AS jsonb), not :p::jsonb — text() drops a bind param
                # followed by a :: cast under asyncpg.
                r2 = await session.execute(
                    text(
                        """
                        UPDATE futures_markets
                        SET market_metadata =
                            COALESCE(market_metadata, '{}'::jsonb)
                            || jsonb_build_object('volume_evidence', CAST(:receipt AS jsonb))
                        WHERE id = :mid
                        """
                    ),
                    {"receipt": json.dumps(receipt), "mid": t.market_id},
                )
                counts["receipts_written"] += r2.rowcount
            await session.commit()

    result = {
        "repair": "polymarket-evidence",
        "applied": bool(apply),
        "counts": counts,
        "by_age_band": by_band,
        "next_cursor": next_cursor,
        "stopped_before": stopped_before,
        "cap": cap,
        "sweep_floor": PM_SWEEP_FLOOR.isoformat(),
        "ordering": "oldest-first WITHIN the floor (gotcha #41 / CAL-P009)",
    }
    # "It returned" is not "it worked" (gotcha #53 / task_verdict). A pass that
    # examined markets and produced no evidence at all is a REAL state and it is
    # said out loud, not left for a reader to infer from four zeros.
    productive = counts["traded"] + counts["confirmed_zero"] + counts["unaddressable"]
    if counts["markets_examined"] and productive == 0:
        result["success"] = False
        result["verdict"] = (
            f"ZERO-YIELD: {counts['markets_examined']} markets examined, every one "
            "INDETERMINATE. That is a venue/transport failure, not an absence of "
            "evidence. Nothing was written."
        )
    else:
        result["success"] = True
    logger.info("Polymarket evidence repair: %s", result["counts"])
    return result
