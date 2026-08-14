"""Retract the Kalshi losses the venue never declared — #1852's backward repair.

CAL-P056. The forward fix (CAL-P053, live in ``d59c9374`` since 2026-08-14
16:59:38 UTC) stopped the producer. This is the rail for the grades already
written. The judgment — which leg gets what — lives in the pure module
``app/utils/kalshi_fabricated_loss.py``; this file is the DB and the venue.

Two entry points, both on the repairs-as-endpoints rail (gotcha #48 — a repair is
an endpoint that returns its own census, never an incantation):

    POST /api/admin/repairs/kalshi-fabricated-loss-census        # never writes
    POST /api/admin/repairs/kalshi-fabricated-loss?apply=false   # dry-run plan
    POST /api/admin/repairs/kalshi-fabricated-loss?apply=true&limit=40
    ...re-invoke with ?offset=<next_offset> while ``exhausted`` is false

RULING 054 — the exclusions are COUNTED, not skipped. Every market this rail
cannot repair leaves with a named verdict and a number: ``provably_purged``
(the venue no longer holds it, banded against the MEASURED bound in
``kalshi_retention``, never a hand-rolled day count), ``unexplained_absence``
(empty at the venue while still INSIDE retention — a different fact, kept
separate per gotcha #53), ``unknown`` (lookup failed — gotcha #36 says that is
not an absence), ``contradictory_venue``, and the per-leg ``not_at_venue``
(mechanism 2, the ticker mismatch: diagnosed, sampled, never written).

RULING 049 / 053 — the acceptance criterion must be able to FAIL. It is not "0
all-loser markets remain", which is arithmetic over a population this rail
defines. It is: **for every leg written, the venue's own answer for that exact
ticker, in the same call, said so** — and the after-census re-reads the rows from
the database rather than trusting the write count. A run that repairs nothing and
a run with nothing to repair report different things (``examined`` versus
``population``), because "it returned" is not "it worked".

GOTCHA #54 / the not-run discipline. Both the census and the work selection run
under an explicit ``SET LOCAL statement_timeout``. On expiry the call returns
``measured: false`` with the reason — an unbounded query that dies is an ABSENT
measurement, never a clean zero.

WHAT THIS DOES NOT TOUCH: prices. ``calibration_probability``,
``current_probability`` and the ``opening_*`` family are left exactly as they
are. This repair corrects a claim about the OUTCOME, and inventing a price to go
with it would be the same class of error one layer down.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text

from app.utils.kalshi_fabricated_loss import (
    POPULATION_HAVING_SQL,
    RETENTION_BAND_SQL,
    RETRACTION_SOURCE,
    classify_leg,
    classify_market,
)
from app.utils.kalshi_retention import (
    AT_RISK_AGE_DAYS,
    MEASURED_ON,
    PROVABLY_PURGED_AGE_DAYS,
)

logger = logging.getLogger(__name__)

#: Hard ceiling on markets written per call. A module constant, NOT a parameter,
#: so "capped" cannot be dialled off mid-run (the winner-field-repair discipline).
APPLY_MARKET_CAP = 40

#: TOTAL wall-clock budget for a call, measured from entry — not a venue-phase
#: budget. The work selection costs ~11s against production before a single
#: Kalshi fetch happens, so a per-phase budget would silently double the real
#: ceiling; the web dyno's 30s HTTP wall does not care which phase spent it. A
#: partial page with a resume offset is a NORMAL outcome and says so, rather than
#: reporting itself exhausted.
_MAX_SECONDS = 25.0

#: Statement budgets for the two expensive reads, both MEASURED against
#: production PostgreSQL on 2026-08-14 by executing these exact strings through
#: the read-only rail (EXPLAIN ANALYZE): the census plan ran 10.8s over 3,354,623
#: outcome rows, and the work selection shares its scan. The budgets are those
#: numbers plus headroom, and an expiry returns a verdict rather than a 500.
_CENSUS_TIMEOUT_MS = 22_000
_SELECT_TIMEOUT_MS = 18_000

#: Legs fetched per venue page. Kalshi caps this at 1000; the biggest observed
#: affected event (a PGA round-leader field) carried 152.
_VENUE_PAGE = 1000
_VENUE_MAX_PAGES = 3


# ---------------------------------------------------------------------------
# Census — dry-run ONLY, and registered under its own name so it can be run
# without going anywhere near the write path.
# ---------------------------------------------------------------------------

_CENSUS_SQL = f"""
    SELECT fm.source AS source,
           fm.mutually_exclusive AS mutex,
           {RETENTION_BAND_SQL} AS retention_band,
           COUNT(*) AS markets,
           SUM(mx.n_out) AS outcomes
    FROM (
      SELECT fo.market_id,
             COUNT(*) AS n_out
      FROM futures_outcomes fo
      GROUP BY fo.market_id
      HAVING {POPULATION_HAVING_SQL}
    ) mx
    JOIN futures_markets fm ON fm.id = mx.market_id
    GROUP BY 1, 2, 3
    ORDER BY 4 DESC
"""


async def census(session, apply: bool = False) -> dict[str, Any]:
    """The standing population, split by source x shape x retention band.

    ``apply`` is accepted and IGNORED — this never writes.

    The split is the point. On 2026-08-14 the Kalshi half of this population was
    8,231 markets, of which 1,414 are provably past the retention bound: they
    cannot be adjudicated by the venue at any budget, and ruling 054 says that
    number is published rather than quietly dropped from a denominator.
    """
    started = time.monotonic()
    try:
        await session.execute(
            text(f"SET LOCAL statement_timeout = {_CENSUS_TIMEOUT_MS}")
        )
        rows = (await session.execute(text(_CENSUS_SQL))).all()
    except Exception as e:  # noqa: BLE001 - the verdict IS the return value
        await session.rollback()
        return {
            "measured": False,
            "reason": f"census did not complete: {type(e).__name__}: {str(e)[:200]}",
            "statement_timeout_ms": _CENSUS_TIMEOUT_MS,
            "note": (
                "NOT RUN, not zero. An unbounded query that dies is an absent "
                "measurement; reporting 0 here would be inventing one."
            ),
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    breakdown = [
        {
            "source": r.source,
            "mutually_exclusive": r.mutex,
            "retention_band": r.retention_band,
            "markets": r.markets,
            "outcomes": int(r.outcomes or 0),
        }
        for r in rows
    ]
    kalshi = [b for b in breakdown if b["source"] == "kalshi"]

    def _sum(rows_, key, **match):
        return sum(
            r[key] for r in rows_ if all(r[k] == v for k, v in match.items())
        )

    return {
        "measured": True,
        "breakdown": breakdown,
        "totals": {
            "markets": _sum(breakdown, "markets"),
            "outcomes": _sum(breakdown, "outcomes"),
        },
        "kalshi": {
            "markets": _sum(kalshi, "markets"),
            "outcomes": _sum(kalshi, "outcomes"),
            "repairable_bands": _sum(kalshi, "markets", retention_band="reachable")
            + _sum(kalshi, "markets", retention_band="at_risk")
            + _sum(kalshi, "markets", retention_band="future_date"),
            "declared_exclusion_provably_purged": _sum(
                kalshi, "markets", retention_band="provably_purged"
            ),
            "at_risk_before_the_cliff": _sum(
                kalshi, "markets", retention_band="at_risk"
            ),
        },
        "retention_bounds": {
            "at_risk_age_days": AT_RISK_AGE_DAYS,
            "provably_purged_age_days": PROVABLY_PURGED_AGE_DAYS,
            "measured_on": MEASURED_ON,
            "note": (
                "Skipping work uses the UPPER bound, so the at_risk band is still "
                "attempted (fail-open). It is banded only to make the count that "
                "is about to expire visible while it can still be saved."
            ),
        },
        "elapsed_s": round(time.monotonic() - started, 1),
    }


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

#: Work selection. It reuses :data:`POPULATION_HAVING_SQL` verbatim, so the
#: census's population and the repair's work list are the SAME predicate by
#: construction rather than by two people keeping two queries in agreement.
#:
#: The shape is measured, not chosen. The first version asked the three questions
#: as correlated EXISTS / NOT EXISTS / COUNT subqueries on ``futures_markets``,
#: which reads better and cost **16.2s** against production (EXPLAIN ANALYZE,
#: 2026-08-14: a 184,333-loop nested join). The grouped-aggregate form below asks
#: them once, in one pass, and costs **10.8s** for the whole population. That
#: difference is the entire reason this rail fits inside a web request.
#:
#: OLDEST-FIRST WITHIN A FLOOR — both halves, because CAL-P009's finding is that
#: either alone is fatal: newest-first never reaches the old tail, and
#: oldest-first with no floor spends the whole budget on rows that are already
#: permanently purged. The floor is the MEASURED purge bound, so this walks
#: exactly the population the venue can still answer for, and it reaches the
#: at-risk band before the cliff does.
#:
#: ⚠️ CAL-P057 MEASURED A THIRD ORDERING TRAP IN THIS SAME ``ORDER BY``, and it is
#: gotcha #41's own closing line — "ordering is never the whole answer; ask what
#: the ordering starts on." Oldest-first-within-a-floor is correct for the PAST.
#: But ``resolution_date >= NOW() - purge_bound`` also admits every FUTURE-dated
#: market, and ``ORDER BY fm.resolution_date ASC`` sorts those DEAD LAST — after
#: every past-dated row in the band. Measured 2026-08-14: **3,913 Kalshi markets in
#: this population carry a resolution_date that has not yet arrived**, which is
#: ~48% of the Kalshi backlog, and they sit behind ~2,887 past-dated markets that
#: the walk reaches first. They are also the cohort MOST likely to still be
#: answerable at the venue. An operator draining this rail page by page will not
#: reach them until the very end. Shard with ``?sport=`` — or, when the future_date
#: cohort is the target, note that it is reachable only by exhausting the offset.
#: This is NOT fixed here: changing the sort is a design decision for the attended
#: pass, and CAL-P009's lesson is that swapping one ordering for another without
#: asking what it starts on is how the last two of these were created.
#:
#: NO ``status = 'resolved'`` FILTER, deliberately. The obvious version had one,
#: and measuring it showed it selected 2,973 markets out of a 6,817-market
#: reachable population — because #1818's finding is that Kalshi markets sit at
#: ``status='open'`` long after the venue settled them. Requiring our own status
#: column to agree would rebuild the exact blind spot that issue named. The
#: venue's answer is the authority here; our status column is not consulted.
_WORK_SQL = f"""
    SELECT fm.id AS market_id,
           fm.external_id AS event_ticker,
           fm.mutually_exclusive AS mutex,
           fm.llm_sport_category AS sport,
           fm.status AS our_status,
           EXTRACT(EPOCH FROM (NOW() - fm.resolution_date)) / 86400.0 AS age_days
    FROM (
      SELECT fo.market_id,
             COUNT(*) AS n_out
      FROM futures_outcomes fo
      GROUP BY fo.market_id
      HAVING {POPULATION_HAVING_SQL}
    ) mx
    JOIN futures_markets fm ON fm.id = mx.market_id
    WHERE fm.source = 'kalshi'
      AND fm.resolution_date IS NOT NULL
      AND fm.resolution_date >= NOW() - INTERVAL '{PROVABLY_PURGED_AGE_DAYS} days'
      AND (:sport IS NULL OR fm.llm_sport_category = :sport)
    ORDER BY fm.resolution_date ASC, fm.id ASC
    LIMIT :lim OFFSET :off
"""


async def _legs(session, market_id: int) -> list[Any]:
    return (
        await session.execute(
            text(
                """
                SELECT id, external_id, is_winner, resolution_source
                FROM futures_outcomes
                WHERE market_id = :mid
                ORDER BY id
                """
            ),
            {"mid": market_id},
        )
    ).all()


async def _fetch_venue(service, event_ticker: str) -> tuple[list[dict] | None, str]:
    """Ask the venue for every market under this event ticker.

    Returns ``(markets, note)``. ``None`` markets means the lookup did not
    answer — 404 or transport error, indistinguishable at this boundary
    (gotcha #36), so it must never be read as "the event has no markets".
    """
    collected: list[dict] = []
    cursor = None
    try:
        for _ in range(_VENUE_MAX_PAGES):
            markets, cursor = await service.get_markets(
                status=None, event_ticker=event_ticker, limit=_VENUE_PAGE, cursor=cursor
            )
            collected.extend(markets or [])
            if not cursor or not markets:
                break
        return collected, "ok"
    except Exception as e:  # noqa: BLE001
        status = getattr(getattr(e, "response", None), "status_code", None)
        return None, f"lookup_failed:{status or type(e).__name__}"


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
    sport: str | None = None,
) -> dict[str, Any]:
    """Per-leg retraction/restoration against the venue's own declaration.

    Dry-run by default. See the module docstring for the contract and
    ``app/utils/kalshi_fabricated_loss.py`` for the judgment.
    """
    from app.services.kalshi_api import KalshiAPIService

    started = time.monotonic()
    window = min(int(limit or APPLY_MARKET_CAP), APPLY_MARKET_CAP)
    cursor = max(int(offset or 0), 0)

    try:
        await session.execute(
            text(f"SET LOCAL statement_timeout = {_SELECT_TIMEOUT_MS}")
        )
        rows = (
            await session.execute(
                text(_WORK_SQL), {"lim": window, "off": cursor, "sport": sport}
            )
        ).all()
    except Exception as e:  # noqa: BLE001
        await session.rollback()
        return {
            "measured": False,
            "reason": f"work selection did not complete: {type(e).__name__}: {str(e)[:200]}",
            "statement_timeout_ms": _SELECT_TIMEOUT_MS,
            "hint": (
                "Shard with ?sport=<llm_sport_category>. The global sort over the "
                "filtered market set is the cost; a sharded sort is not."
            ),
            "note": "NOT RUN, not zero.",
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    market_verdicts: dict[str, int] = {}
    leg_verdicts: dict[str, int] = {}
    examined = 0
    markets_written = 0
    winners_restored = 0
    losses_retracted = 0
    timed_out = False
    excluded: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    mismatch_samples: list[dict[str, Any]] = []

    def _bump(d: dict[str, int], k: str, n: int = 1) -> None:
        d[k] = d.get(k, 0) + n

    service = KalshiAPIService()
    try:
        for row in rows:
            if time.monotonic() - started > _MAX_SECONDS:
                timed_out = True
                break
            examined += 1

            venue_markets, note = await _fetch_venue(service, row.event_ticker)
            verdict, detail = classify_market(
                venue_markets, row.age_days, mutually_exclusive=row.mutex
            )
            _bump(market_verdicts, verdict)

            if verdict != "answered":
                _bump(excluded, verdict)
                if len(samples) < 12:
                    samples.append(
                        {
                            "market_id": row.market_id,
                            "event_ticker": row.event_ticker,
                            "age_days": round(float(row.age_days), 1),
                            "verdict": verdict,
                            "lookup": note,
                            **detail,
                        }
                    )
                continue

            by_ticker = {m.get("ticker"): m for m in (venue_markets or [])}
            legs = await _legs(session, row.market_id)

            planned: list[tuple[int, str]] = []
            for leg in legs:
                vm = by_ticker.get(leg.external_id)
                leg_verdict = classify_leg(
                    bool(leg.is_winner),
                    leg.resolution_source,
                    (vm or {}).get("status"),
                    (vm or {}).get("result"),
                    present_at_venue=vm is not None,
                )
                _bump(leg_verdicts, leg_verdict)
                if leg_verdict == "not_at_venue" and len(mismatch_samples) < 12:
                    # Mechanism 2. Recorded so it stops being a sample nobody
                    # reads, and deliberately never written.
                    mismatch_samples.append(
                        {
                            "market_id": row.market_id,
                            "event_ticker": row.event_ticker,
                            "our_ticker": leg.external_id,
                            "venue_tickers_sample": sorted(by_ticker)[:3],
                            "venue_legs": len(by_ticker),
                        }
                    )
                if leg_verdict in ("restore_winner", "retract_fabricated"):
                    planned.append((leg.id, leg_verdict))

            if not planned:
                continue

            if not apply:
                markets_written += 1
                winners_restored += sum(
                    1 for _, v in planned if v == "restore_winner"
                )
                losses_retracted += sum(
                    1 for _, v in planned if v == "retract_fabricated"
                )
                continue

            if markets_written >= APPLY_MARKET_CAP:
                break

            for leg_id, leg_verdict in planned:
                if leg_verdict == "restore_winner":
                    r = await session.execute(
                        text(
                            """
                            UPDATE futures_outcomes
                            SET is_winner = true,
                                resolution_source = 'api_settlement',
                                last_updated = NOW()
                            WHERE id = :id AND NOT is_winner
                            """
                        ),
                        {"id": leg_id},
                    )
                    winners_restored += r.rowcount
                else:
                    # The one permitted authority downgrade, and it is guarded to
                    # the exact badge being retracted: if a concurrent grader has
                    # already replaced api_settlement with a real result, this is
                    # a no-op rather than a clobber.
                    r = await session.execute(
                        text(
                            """
                            UPDATE futures_outcomes
                            SET resolution_source = :retraction,
                                last_updated = NOW()
                            WHERE id = :id
                              AND resolution_source = 'api_settlement'
                              AND NOT is_winner
                            """
                        ),
                        {"id": leg_id, "retraction": RETRACTION_SOURCE},
                    )
                    losses_retracted += r.rowcount
            markets_written += 1
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001
            pass

    if apply and markets_written:
        await session.commit()

    after = None
    if apply and rows:
        # Re-READ the rows rather than trusting the rowcounts: a mutation that
        # fails to apply reports green, so the proof is the database's answer.
        after = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) FILTER (WHERE resolution_source = :retraction)
                               AS retracted_now,
                           COUNT(*) FILTER (WHERE is_winner) AS winners_now
                    FROM futures_outcomes
                    WHERE market_id = ANY(:ids)
                    """
                ),
                {
                    "retraction": RETRACTION_SOURCE,
                    "ids": [r.market_id for r in rows],
                },
            )
        ).one()
        after = {
            "retracted_now": after.retracted_now,
            "winners_now": after.winners_now,
            "scope": "the markets in THIS window only",
        }

    return {
        "apply": apply,
        "window": {
            "limit": window,
            "offset": cursor,
            "returned": len(rows),
            "sport": sport,
        },
        "examined": examined,
        "market_verdicts": market_verdicts,
        "leg_verdicts": leg_verdicts,
        "markets_written" if apply else "markets_would_write": markets_written,
        "winners_restored" if apply else "winners_would_restore": winners_restored,
        "losses_retracted" if apply else "losses_would_retract": losses_retracted,
        # Ruling 054: an exclusion is a number with a name, never a silent skip.
        "declared_exclusions": excluded,
        "excluded_examples": samples,
        "ticker_mismatch_examples": mismatch_samples,
        "after_reread": after,
        "next_offset": cursor + examined,
        "exhausted": (not timed_out) and len(rows) < window,
        "stopped_on_time_budget": timed_out,
        "elapsed_s": round(time.monotonic() - started, 1),
        "apply_market_cap": APPLY_MARKET_CAP,
        "retraction_source": RETRACTION_SOURCE,
        "prices_touched": False,
    }
