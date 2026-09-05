"""Retract the Kalshi losses the venue never declared — #1852's backward repair.

CAL-P056. The forward fix (CAL-P053, live in ``d59c9374`` since 2026-08-14
16:59:38 UTC) stopped the producer. This is the rail for the grades already
written. The judgment — which leg gets what — lives in the pure module
``app/utils/kalshi_fabricated_loss.py``; this file is the DB and the venue.

Two entry points, both on the repairs-as-endpoints rail (gotcha #48 — a repair is
an endpoint that returns its own census, never an incantation):

    POST /api/admin/repairs/kalshi-fabricated-loss-census        # never writes
    POST /api/admin/repairs/kalshi-fabricated-loss?apply=false   # dry-run plan
    ...returns ``plan_hash`` and persists the plan artifact
    POST /api/admin/repairs/kalshi-fabricated-loss?apply=true&plan_hash=<hash>
    ...then drain with ?after_date=<..>&after_id=<..> from ``next_cursor``

CAL-P1008 — THE CAPTURE IS PART OF THE RUNBOOK, not housekeeping after it. The
durable plan slot (:data:`PLAN_IDENTITY`) holds ONE plan and a drain over
:data:`APPLY_MARKET_CAP` markets per call runs many, so batch N+1's dry-run
destroys the only per-leg record of what batch N's RESTORE arm touched — that arm
writes ``api_settlement`` back over ``api_settlement`` and leaves no marker to
find its rows by afterwards. Every dry-run response therefore carries
``plan_artifact``: the byte-identical banked payload, each leg with its verdict
and the prior state the apply compares on. Save it before the next dry-run::

    for each batch N:
        apply=false  → save the WHOLE response as batchN-plan.json, read it
        apply=true&plan_hash=<hash from that response>
                     → save the whole response as batchN-applied.json
    ...then re-census; finished is the addressed bands measuring 0.

CAL-P1008-R (CERT-965) — AND THE UNDO IS A COMMAND, not a capture discipline.
The block above makes the plan capturable, but capture is then an operator step,
and an undo that exists only if a human remembered to save a file is the same
hole one door down. So the apply banks the pre-image itself, at a per-plan
address, BEFORE its first UPDATE — and refuses to write a single row if it
cannot. To reverse one batch::

    POST /api/admin/repairs/kalshi-fabricated-loss-restore?plan_hash=<hash>
    POST /api/admin/repairs/kalshi-fabricated-loss-restore?apply=true&plan_hash=<hash>

Dry-run by default; the `plan_hash` is in the apply response's ``undo`` block.
The response capture above is still worth keeping — it is a second copy,
off-box, and it is what you read to decide *whether* to undo.

CAL-P1008-R2 (CERT-970) — AND THE RESTORE IS BOUND TO WHAT WAS **WRITTEN**.
Binding it to the plan was a data-corruption bug, not a nicety. Specimen: a
grader moves a planned leg to ``(true, api_settlement)`` — the state a
successful apply produces — so the apply's compare-and-set skips it and never
writes it; a plan-bound restore then finds its post-apply predicate satisfied
and sets ``is_winner`` back to false, destroying a real grade. So the apply
banks a SECOND record after its commit — :func:`applied_identity`, holding only
the rowcount-1 writes — and every write carries
``last_updated = :applied_version``, a value the apply chooses. The restore
requires both: membership in that record, and that exact version still on the
row. The version is what catches the case values cannot — a regrade to the SAME
values after a successful apply. Rows committed with no applied receipt make the
apply report ``success: false``: they are rows nothing can reverse.

CAL-P058 — WHAT C-CERT-1852 CHANGED HERE, and it is the write protocol, not the
judgment. The certification confirmed the judgment is genuinely per-leg and that
the four venue specimens reproduce; it BLOCKED the branch on five defects in how
the attended pass is driven. Four of them are answered in this file:

1. **The cursor is a KEYSET, not an OFFSET.** Every successful page removes its
   own rows from ``POPULATION_HAVING_SQL``, so ``OFFSET cursor + examined``
   stepped over exactly as many untouched markets as it had just repaired. A
   100-row model produced page 1 = 1–40, page 2 at offset 40 = 81–100,
   ``exhausted: true``, rows 41–80 never examined. The cursor now names the
   position ``(resolution_date, market_id)`` the walk REACHED, which is stable
   under deletion, and the rail scores its own telemetry against the canonical
   ``repair-cap-cursor-skip`` contract before returning.
2. **Apply is bound to the dry-run somebody read.** ``apply=true`` no longer
   re-derives anything: it loads the content-addressed plan artifact the
   dry-run wrote, refuses unless the operator's ``plan_hash`` matches the
   artifact's own re-derived address, and writes ONLY the leg ids that plan
   names. No work SQL, no venue call, no classification at apply time.
3. **Both write forms are compare-and-set.** The restore carried no guard, so a
   concurrent grader replacing ``api_settlement`` between the read and the write
   would have been overwritten by a stale ``api_settlement``. Every statement
   now carries the EXACT prior ``(is_winner, resolution_source)`` the dry-run
   read, and a rowcount of zero is a named ``concurrent_drift`` that reports and
   skips — never a silent overwrite and never a silent success.
4. **The calibration invalidation is EXECUTED, not declared in prose.** See
   :func:`invalidate_calibration_generation`. A run that wrote rows and could not
   invalidate returns ``success: false``.

CAL-P062 — WHAT C-CERT-1852-**R2** CHANGED, and it is finding 4 again, twice. The
re-certification passed 1, 2, 3 and 5 and blocked on two paths by which the
invalidation could still report green having done nothing:

4a. **The main checkpoint is AFTER-READ, not acknowledged.** Only the staged
    cursor was re-read; the checkpoint's own publish status was taken as proof.
    A no-op publisher scored ``invalidated``, and ``superseded`` — the case where
    a newer checkpoint's banked phases are provably still sitting there — counted
    as success. The record in the store is now read back and judged by
    ``app/utils/calibration_invalidation.main_checkpoint_is_invalidation``.
4b. **The invalidation obligation OUTLIVES the response.** Rows are committed
    before the curve is invalidated, so a failed invalidation is a debt; that
    debt used to vanish with the HTTP response. A retry of the same plan then
    drifted on its own committed row, called the invalidation with an empty id
    set, got ``nothing_written`` and returned ``success: true``. The debt now
    lives at :data:`OBLIGATION_IDENTITY`, a retry retries that exact
    obligation's market ids, and ``nothing_written`` is a discharge only for a
    plan proven never to have written — never for one whose legs drifted, and
    never for one carrying an open debt.
4c. **The debt is staged in the transaction that creates it** (CAL-P1009-R,
    CERT-1872). "Before the invalidation" was still after the COMMIT, and a
    process loss in that interval left a stale published curve with no durable
    retry handle at all. Both writers of the one slot — the apply and the
    restore — now stage their OPEN debt through :func:`_stage_obligation` in the
    same transaction as the rows, gated on containment read back from the store,
    and commit once. Rows and the debt they owe land together or not at all; a
    staging failure rolls the whole thing back and no row moves.

The fifth finding is answered in ``app/utils/kalshi_fabricated_loss.py``: the
venue-to-stored-leg join now lives in :func:`~app.utils.kalshi_fabricated_loss.plan_market_legs`,
which is the path production takes AND the path the specimen replay enters
through — there is no second mapping written in the test file.

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
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.utils.calibration_invalidation import (
    INVALIDATION_OBLIGATION_SCHEMA,
    RESTORE_DISCHARGES,
    discharge_obligation,
    invalidation_discharged,
    main_checkpoint_is_invalidation,
    new_obligation,
    obligation_contains,
    obligation_is_open,
    obligation_leg_ids,
    obligation_market_ids,
    obligation_plan_hash,
    obligation_retry_instruction,
)
from app.utils.kalshi_fabricated_loss import (
    POPULATION_HAVING_SQL,
    REPAIRABLE_SOURCE,
    RETENTION_BAND_SQL,
    RETRACTION_SOURCE,
    WRITING_VERDICTS,
    classify_market,
    plan_market_legs,
)
from app.utils.kalshi_retention import (
    AT_RISK_AGE_DAYS,
    MEASURED_ON,
    PROVABLY_PURGED_AGE_DAYS,
)
from app.utils.repair_apply_plan import (
    APPLIED_RECEIPT_SCHEMA,
    APPLY_PLAN_SCHEMA,
    REASON_APPLIED_MISSING,
    REASON_CONCURRENT_DRIFT,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_UNREADABLE,
    PlannedLeg,
    approved_leg_index,
    bind_apply,
    applied_receipt_contains,
    build_applied_receipt,
    build_plan,
    decode_applied_receipt,
    decode_plan,
    evaluate_repair_contract,
    keyset_after,
    mutations_outside_approved,
    plan_reason_for_read,
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
#:
#: RE-MEASURED 2026-08-14 ~19:5x UTC on the KEYSET form, and the number MOVED —
#: recorded rather than smoothed over, because a stale measured claim in
#: shipping code is the thing this rail keeps catching in other people's work.
#: Four executions of the exact shipping string (`explain+analyze`, so it really
#: ran), 6,816 rows in the population subquery, LIMIT 5:
#:
#:     cold  17.99s   ·   17.57s        warm  5.03s   ·   5.72s
#:     plus ONE contended run that exceeded the 25s ceiling entirely
#:
#: So a COLD first page sits within ~0.1s of ``_SELECT_TIMEOUT_MS`` and can trip
#: it. That is left as-is on purpose. Raising the budget past the web dyno's 30s
#: HTTP wall converts an honest ``measured: false`` — which arrives WITH the
#: ``?sport=`` shard hint the operator needs — into a dead request that says
#: nothing. The keyset did not cause this: it removed an OFFSET, which only ever
#: made the sort more expensive. An attended drain should expect to shard.
_CENSUS_TIMEOUT_MS = 22_000
_SELECT_TIMEOUT_MS = 18_000

#: Legs fetched per venue page. Kalshi caps this at 1000; the biggest observed
#: affected event (a PGA round-leader field) carried 152.
_VENUE_PAGE = 1000
_VENUE_MAX_PAGES = 3

#: Durable identity of the reviewed plan artifact. ONE slot: a dry-run
#: overwrites it, and the content address is what stops an operator applying the
#: page they read two pages ago.
#:
#: CAL-P1008 — that one slot is also the only record of WHICH LEG GOT WHICH
#: VERDICT, and that is the undo. The prior state is not the hard part: both
#: writing verdicts require ``is_winner = false`` and
#: :data:`REPAIRABLE_SOURCE`, so the pre-image is a rail-wide constant, not a
#: per-leg fact. What is per-leg is the ARM.
#:
#: * Retraction is self-identifying afterwards — it stamps
#:   :data:`RETRACTION_SOURCE`, so its rows can be found by that marker alone.
#: * Restore leaves NO marker. It sets ``is_winner = true`` and writes
#:   ``api_settlement`` back over ``api_settlement``, so a restored leg is
#:   byte-identical to a Kalshi winner nobody ever touched. Only the plan says
#:   which ones they were, and ``plan_leg_ids`` in the response is both arms
#:   mixed together with no verdict on them.
#:
#: So batch N+1's dry-run overwrites the only thing that can reverse batch N's
#: restore arm. The dry-run therefore hands the whole artifact back in
#: ``plan_artifact`` — see :func:`_dry_run` — so the operator's captured response
#: IS the backup and the durable slot is a convenience, not the record of last
#: resort.
PLAN_IDENTITY = "calibration:repair:kalshi_fabricated_loss:plan"


def declared_curve_movement(
    *, winners_restored: int, losses_retracted: int
) -> dict[str, Any]:
    """Ruling 050's armed control, in the direction CAL-P057 MEASURED.

    An armed control is a prediction made BEFORE the write, stated precisely
    enough that being wrong is visible. The rail's own docstring used to predict
    the wrong sign, so the numbers replace it:

    **The retraction arm moves the published curve by ZERO.** This rail's
    population is the same predicate as the curve's own ``no_winner_markets``
    exclusion (a resolved market with ``n_outcomes >= 2`` and ``win_count = 0``),
    and CAL-P057 measured the whole 0–86 day work band in 15 shards with none
    skipped: **2,887 of 2,887 target markets — 100%, 18,688 legs — are already
    excluded.** A row that is not on the curve cannot be removed from it.

    **The movement, if any, is an ADDITION.** A ``restore_winner`` flips
    ``win_count`` 0 → 1, the market LEAVES ``no_winner_markets``, and its whole
    surviving leg set is ADMITTED. So the predicted sign is **positive n**, and
    the magnitude to declare is the count of admitted legs, never retracted ones.

    **A curve that moves on the retraction arm is a HALT, not a success.** It
    would mean the population predicate and the exclusion predicate have drifted
    apart, which invalidates the reason this repair was safe to run at all.
    """
    return {
        "ruling": "050 — armed control, declared BEFORE the recompute",
        "retraction_arm": {
            "legs_retracted": losses_retracted,
            "predicted_curve_delta": 0,
            "why": (
                "the rail's population IS the curve's own no_winner_markets "
                "exclusion — measured 2,887/2,887 markets (100%), 18,688 legs, "
                "already excluded (CAL-P057, 15 shards, none skipped)"
            ),
            "if_it_moves": (
                "HALT. A non-zero delta on this arm means the population and "
                "exclusion predicates have drifted apart, which is the premise "
                "the repair's safety rests on."
            ),
        },
        "restore_arm": {
            "winners_restored": winners_restored,
            "predicted_sign": "positive — an ADDITION, not a subtraction",
            "why": (
                "win_count 0 -> 1 makes the market leave no_winner_markets, "
                "ADMITTING its whole surviving leg set to the curve"
            ),
            "declare": "the count of admitted legs, never the retracted ones",
        },
        "measure_after": (
            "recompute, then compare the published curve's n and "
            "no_winner_filter.excluded against the pre-apply census"
        ),
    }


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
#: CAL-P058 REPLACED THE OFFSET WITH A KEYSET, and the reason is that this rail
#: DELETES FROM ITS OWN POPULATION. A repaired market stops satisfying
#: ``POPULATION_HAVING_SQL`` — that is the whole point of repairing it — so
#: ``OFFSET n`` on the next call counts n rows into a result set that is now n
#: rows shorter, and steps over exactly the markets it just failed to reach.
#: C-CERT-1852 modelled it at 100 rows: page 1 = 1–40, page 2 at offset 40 =
#: 81–100, ``exhausted: true``, and rows 41–80 never examined by anything. The
#: keyset predicate names a POSITION in the sort order instead of a COUNT of
#: rows behind it, and a position is invariant under deletion. It also composes
#: with the wall-clock stop: the cursor is the last row EXAMINED, not the last
#: row returned, so a page that ran out of budget resumes inside its own page
#: rather than past it.
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
           fm.resolution_date AS resolution_date,
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
      -- CAST is NOT decoration. asyncpg prepares this statement with no
      -- parameter types, so Postgres must infer them from the text alone, and
      -- the FIRST occurrence of a parameter fixes its type: `$1 IS NULL` fixes
      -- `$1` as `unknown`, the later `= $1` can no longer resolve it, and the
      -- prepare dies with `AmbiguousParameterError: could not determine data
      -- type of parameter $1` — before a row is read, whatever value is bound.
      -- That is why the keyset below casts both halves, and why every sibling
      -- rail writes `:sport::text` on BOTH sides (`repair_polymarket_leg_label`
      -- :457-458, :758). This line was the one that did not, so the drain's
      -- endpoint has never completed a work selection.
      AND (CAST(:sport AS text) IS NULL OR fm.llm_sport_category = CAST(:sport AS text))
      AND (
            CAST(:after_date AS timestamptz) IS NULL
         OR (fm.resolution_date, fm.id)
              > (CAST(:after_date AS timestamptz), CAST(:after_id AS bigint))
          )
    ORDER BY fm.resolution_date ASC, fm.id ASC
    LIMIT :lim
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

# ---------------------------------------------------------------------------
# The reviewed-plan artifact (C-CERT-1852 finding 2)
# ---------------------------------------------------------------------------


async def _save_plan(plan) -> tuple[bool, str]:
    """Persist the dry-run's plan. ``(ok, note)`` — a failure is REPORTED.

    On the durable snapshot rail rather than Redis, deliberately: the sentinel
    evidence lesson (a 14-day SETEX on a 49.5/50 MB allkeys-lru instance is
    evicted, and the swallowed write failure let a run record evidence that no
    longer existed). An operator who cannot be handed a plan hash must be told
    so, because the next thing they will do is try to apply.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PLAN_IDENTITY,
                schema_version=APPLY_PLAN_SCHEMA,
                payload=plan.as_payload(),
                complete=True,
                source="repair:kalshi-fabricated-loss",
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return False, f"plan persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"plan persist rejected: {result.get('status')}"


async def _load_plan():
    """``(plan, reason)`` — the artifact, re-digested from its own content."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            PLAN_IDENTITY, expected_version=APPLY_PLAN_SCHEMA, max_age_s=14 * 86400
        )
    except Exception as exc:  # noqa: BLE001
        # A raise is "I could not read", never "it is not there" (gotcha #53).
        logger.warning("repair plan read raised: %s", type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not read.ok or read.envelope is None:
        # Carry the durable layer's classification instead of flattening it into
        # prose that the binder cannot match — C-APPLY-PRE-R2 finding 1.
        logger.warning(
            "repair plan artifact not readable: status=%s error_class=%s",
            read.status, read.error_class,
        )
        return None, plan_reason_for_read(read.status, error_class=read.error_class)
    return decode_plan(read.envelope.payload)


# ---------------------------------------------------------------------------
# The UNDO RECEIPT (CAL-P1008-R, CERT-965)
#
# CERT-965 blocked the first CAL-P1008 branch for the right reason. Handing the
# plan back on the dry-run response makes the undo *capturable*, but capture is
# then an operator step, and an undo that exists only if a human remembered to
# `tee` is the same hole one door down. D51 = B(b) asks for a backup WRITTEN
# FIRST and a restore that RUNS.
#
# So: one slot PER PLAN, addressed by the plan's own content hash, written
# before any row is touched, and an apply that cannot bank it does not mutate.
# Per-plan addressing is the whole point — :data:`PLAN_IDENTITY` is one slot and
# batch N+1 overwrites it, which is exactly what left batch N unrecoverable.
# ---------------------------------------------------------------------------

UNDO_RECEIPT_SCHEMA = "kalshi_fabricated_loss_undo_receipt_v1"

#: Receipts are read to REVERSE a write, so they must outlive the drain by a
#: wide margin. A receipt that aged out would read as "nothing to undo", which
#: is the false-green this whole rail is built to refuse.
_RECEIPT_MAX_AGE_S = 365 * 86400


def receipt_identity(plan_hash: str) -> str:
    """One durable slot per plan. Content-addressed, so batches cannot collide."""
    return f"calibration:repair:kalshi_fabricated_loss:receipt:{plan_hash}"


def applied_identity(plan_hash: str) -> str:
    """Where the APPLIED receipt lives — what was written, not what was planned.

    CERT-970: these are two different facts and only one of them may drive a
    restore. See :data:`APPLIED_RECEIPT_SCHEMA` for the specimen.
    """
    return f"calibration:repair:kalshi_fabricated_loss:applied:{plan_hash}"


async def _stage_applied(session, plan_hash: str, written_legs) -> tuple[bool, str, int]:
    """STAGE the applied receipt in the caller's open transaction.

    CAL-P1008-R3 (CERT-1858). Banking this on its own session after the apply's
    commit was still a hole: rows landed, the receipt did not, and the rail
    reported the state honestly — ``reversible: false`` — which is a description
    of an unrecoverable row, not a defence against one. Reporting a hole is not
    closing it.

    So the receipt is staged in the SAME transaction as the outcome mutations
    and the caller commits ONCE (the CERT-851 pattern that
    :func:`publish_snapshot_in_txn` exists for). Rows and their undo record land
    together or not at all; a staging failure is the caller's rollback, and the
    rows are left exactly as they were.

    Read-then-merge-then-stage: a retry of a partly-applied plan must ADD its
    legs, and an apply that wrote nothing must not blank the record of one that
    wrote something. The read is on the SAME session, so it sees this
    transaction's own state rather than a stale snapshot beside it.
    """
    from app.services.durable_snapshots import publish_snapshot_in_txn, read_snapshot
    from app.utils.durable_state import DurableEnvelope

    identity = applied_identity(plan_hash)
    existing = None
    try:
        read = await read_snapshot(
            session,
            identity,
            expected_version=APPLIED_RECEIPT_SCHEMA,
            max_age_s=_RECEIPT_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        # Cannot read is NOT "nothing banked" (gotcha #53). Merging onto an
        # unknown base could erase an earlier call's written set, so refuse.
        return False, f"applied receipt read raised: {type(exc).__name__}", 0
    if read.status != "missing":
        if not read.ok or read.envelope is None:
            return False, f"applied receipt unreadable: {read.status}", 0
        existing = read.envelope.payload

    payload = build_applied_receipt(plan_hash, written_legs, existing=existing)
    if not written_legs:
        # Nothing was written, so there is nothing to record and the merge is a
        # no-op by construction. Staging it anyway would leave a durable write
        # pending in a transaction this call never commits.
        return True, "nothing written; receipt unchanged", payload["leg_count"]
    try:
        result = await publish_snapshot_in_txn(
            session,
            DurableEnvelope.build(
                identity=identity,
                schema_version=APPLIED_RECEIPT_SCHEMA,
                payload=payload,
                complete=True,
                source="repair:kalshi-fabricated-loss",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"applied receipt stage raised: {type(exc).__name__}", 0

    # CAL-P1008-R4 (CERT-1863): the STATUS is a note, not the gate. The durable
    # layer answers `superseded` when a newer generation already sits at the
    # identity, and in that case it writes NOTHING — for a plan artifact that
    # still means "a good copy exists", which is why `_save_plan` accepts it,
    # but here it means somebody else's payload is there and mine never landed.
    # Taking it as success committed rows whose undo record did not contain
    # them. So the gate is CONTAINMENT, read back from the store: are the legs
    # this call wrote there, at the versions it wrote?
    status = result.get("status")
    try:
        back = await read_snapshot(
            session,
            identity,
            expected_version=APPLIED_RECEIPT_SCHEMA,
            max_age_s=_RECEIPT_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"applied receipt read-back raised: {type(exc).__name__}", 0
    if back.status == "missing":
        # Nothing at the identity at all after a stage that answered. This is a
        # containment failure, not a store outage: this write did not land.
        return (
            False,
            f"applied receipt absent after staging ({status}): this write did "
            "not land",
            0,
        )
    if not back.ok or back.envelope is None:
        return False, f"applied receipt not readable after staging: {back.status}", 0

    contained, why = applied_receipt_contains(
        back.envelope.payload,
        expected_source_plan_hash=plan_hash,
        written_legs=written_legs,
    )
    if not contained:
        return False, f"applied receipt does not contain this write ({status}): {why}", 0
    return True, f"ok ({status})", payload["leg_count"]


async def _load_applied(plan_hash: str):
    """``(legs, reason)`` for the applied receipt. Never "absent" on a bad read."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            applied_identity(plan_hash),
            expected_version=APPLIED_RECEIPT_SCHEMA,
            max_age_s=_RECEIPT_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("applied receipt read raised: %s", type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if read.status == "missing":
        return None, REASON_APPLIED_MISSING
    if not read.ok or read.envelope is None:
        return None, plan_reason_for_read(read.status, error_class=read.error_class)
    return decode_applied_receipt(
        read.envelope.payload, expected_source_plan_hash=plan_hash
    )


async def _save_receipt(plan) -> tuple[bool, str]:
    """Bank the pre-image BEFORE the first UPDATE. ``(ok, note)``.

    The payload is the plan's own artifact, unchanged, so the receipt re-decodes
    through :func:`decode_plan` and re-derives its own address — a receipt that
    was edited or truncated in the store cannot be mistaken for a good one.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=receipt_identity(plan.plan_hash),
                schema_version=UNDO_RECEIPT_SCHEMA,
                payload=plan.as_payload(),
                complete=True,
                source="repair:kalshi-fabricated-loss",
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return False, f"receipt persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"receipt persist rejected: {result.get('status')}"


async def _load_receipt(plan_hash: str):
    """``(plan, reason)`` for a banked receipt. Never "absent" on a failed read."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            receipt_identity(plan_hash),
            expected_version=UNDO_RECEIPT_SCHEMA,
            max_age_s=_RECEIPT_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo receipt read raised: %s", type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not read.ok or read.envelope is None:
        return None, plan_reason_for_read(read.status, error_class=read.error_class)
    return decode_plan(read.envelope.payload)


# ---------------------------------------------------------------------------
# The invalidation OBLIGATION ledger (C-CERT-1852-R2 specimen two)
#
# One durable slot, deliberately separate from the plan artifact. The plan says
# what SHOULD be written; this says what HAS been written and not yet paid for.
# They have different lifetimes: a plan is superseded by the next dry-run, while
# a debt survives every later call until it is discharged.
# ---------------------------------------------------------------------------

OBLIGATION_IDENTITY = "calibration:repair:kalshi_fabricated_loss:invalidation_obligation"

#: The two writers of that one slot. CAL-P1009: they move the same rows in
#: OPPOSITE directions, so an open debt must say which one made it — the escape
#: from an unpaid invalidation is to re-run the action that created it, and
#: guessing wrong redoes a repair somebody deliberately undid.
OBLIGATION_OWNER_APPLY = "repair:kalshi-fabricated-loss"
OBLIGATION_OWNER_RESTORE = "repair:kalshi-fabricated-loss-restore"

#: An obligation must never age out of visibility. A debt that becomes
#: unreadable because it got old is the same false-green one door down, so the
#: bound is a year and an expiry reads as UNREADABLE (which refuses) rather than
#: as absence (which would let the next apply proceed).
_OBLIGATION_MAX_AGE_S = 365 * 86400


async def _load_obligation() -> tuple[dict[str, Any] | None, str]:
    """``(record, note)``. ``note`` is ``missing`` (no debt) or ``ok``, and any
    other value means UNKNOWN — which the caller must treat as a refusal, never
    as "no obligation"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            OBLIGATION_IDENTITY,
            expected_version=INVALIDATION_OBLIGATION_SCHEMA,
            max_age_s=_OBLIGATION_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"obligation read raised: {type(exc).__name__}"
    if read.status == "missing":
        return None, "missing"
    if not read.ok or read.envelope is None:
        return None, f"obligation unreadable: {read.status}"
    payload = read.envelope.payload
    if not isinstance(payload, dict):
        return None, "obligation malformed"
    return payload, "ok"


async def _save_obligation(record: dict[str, Any]) -> tuple[bool, str]:
    """Persist the debt (or its discharge). A failure is REPORTED, never assumed."""
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=OBLIGATION_IDENTITY,
                schema_version=INVALIDATION_OBLIGATION_SCHEMA,
                payload=record,
                complete=True,
                source="repair:kalshi-fabricated-loss",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"obligation persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"obligation persist rejected: {result.get('status')}"


async def _stage_obligation(session, record: dict[str, Any]) -> tuple[bool, str]:
    """STAGE the debt in the caller's open transaction. ``(ok, note)``.

    CAL-P1009-R (CERT-1872). Banking the OPEN debt on its own session *after*
    the rows were committed left a window with a name: the rows land, the record
    of what they owe does not, and a process loss in between leaves the
    published curve stale with nothing durable naming what would pay it. That is
    the same hole CERT-1858 closed one slot over for the undo receipt, and the
    same answer applies — the debt is staged in the SAME transaction as the row
    mutations and the caller commits ONCE. Rows and the debt they create land
    together or not at all; a staging failure is the caller's rollback, and no
    row moves.

    (The sibling rail ``repair_pm_never_graded`` reaches the same doctrine from
    the other side, opening an intent over the APPROVED set before its first
    write and refusing if it cannot. Here the debt is exactly what was written,
    which is knowable only once the loop has run — so it rides the transaction
    instead of preceding it.)

    Read-back is the gate, never the status: see
    :func:`~app.utils.calibration_invalidation.obligation_contains`.
    """
    from app.services.durable_snapshots import publish_snapshot_in_txn, read_snapshot
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_in_txn(
            session,
            DurableEnvelope.build(
                identity=OBLIGATION_IDENTITY,
                schema_version=INVALIDATION_OBLIGATION_SCHEMA,
                payload=record,
                complete=True,
                source="repair:kalshi-fabricated-loss",
            ),
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return False, f"obligation stage raised: {type(exc).__name__}"

    status = result.get("status")
    try:
        back = await read_snapshot(
            session,
            OBLIGATION_IDENTITY,
            expected_version=INVALIDATION_OBLIGATION_SCHEMA,
            max_age_s=_OBLIGATION_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"obligation read-back raised: {type(exc).__name__}"
    if back.status == "missing":
        return (
            False,
            f"obligation absent after staging ({status}): this write did not land",
        )
    if not back.ok or back.envelope is None:
        return False, f"obligation not readable after staging: {back.status}"

    contained, why = obligation_contains(
        back.envelope.payload,
        plan_hash=record["plan_hash"],
        owner=record["owner"],
        market_ids=record["market_ids"],
        leg_ids=record["leg_ids"],
    )
    if not contained:
        return False, f"obligation does not carry this debt ({status}): {why}"
    return True, f"ok ({status})"


async def _main_checkpoint_after_read() -> tuple[bool, str, str]:
    """Read ``CHECKPOINT_IDENTITY`` back and judge the record that is THERE.

    ``(is_invalidation, why, read_status)``. An absent checkpoint counts: there
    is nothing banked for a resume to read, which is the fact the invalidation
    exists to establish. Every other non-``ok`` read is UNKNOWN and fails.
    """
    from app.services.durable_snapshots import read_snapshot_standalone
    from app.tasks.calibration_main_build import CHECKPOINT_IDENTITY
    from app.utils.calibration_phase_ledger import MAIN_CHECKPOINT_SCHEMA

    try:
        read = await read_snapshot_standalone(
            CHECKPOINT_IDENTITY,
            expected_version=MAIN_CHECKPOINT_SCHEMA,
            max_age_s=14 * 86400,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"MAIN_CHECKPOINT_READ_RAISED:{type(exc).__name__}", "raised"
    if read.status == "missing":
        return (
            True,
            "MAIN_CHECKPOINT_ABSENT — no record, so nothing banked to resume",
            read.status,
        )
    if not read.ok or read.envelope is None:
        return False, f"MAIN_CHECKPOINT_UNREADABLE:{read.status}", read.status
    ok, why = main_checkpoint_is_invalidation(read.envelope.payload)
    return ok, why, read.status


# ---------------------------------------------------------------------------
# Executable calibration invalidation (C-CERT-1852 finding 4)
# ---------------------------------------------------------------------------


async def invalidate_calibration_generation(session, market_ids) -> dict[str, Any]:
    """Discard every banked calibration unit, and PROVE it. Not a docstring.

    C-CERT-1852's fourth finding was that the branch's precondition — "someone
    must answer whether banked calibration units invalidate on this" — supplied
    no command, no expected value, no refusal condition and no endpoint gate.
    CAL-P057 then measured the answer, and the answer makes the gap worse rather
    than better: the generation fingerprint digests
    ``(market_id, source, vm_id, is_grouped)``, every field of which comes from
    ``market_info``/``virtual_market``, sized by ``group_sizes``/``event_sizes``
    which **count markets, not outcomes**. The roster never reads
    ``futures_outcomes`` at all, so a repair that writes only to
    ``futures_outcomes`` is **structurally invisible** to the one mechanism that
    invalidates banked units. Units banked before the repair would resume beside
    units computed after it, under one generation, and nothing would notice.

    So this is the declaration, executed.

    **IT IS WHOLESALE, AND THAT IS FORCED — twice over, both measured.**

    1. *Per-unit invalidation is not expressible on this cursor.* CAL-P034
       replaced the cursor's per-unit rows with a single running ``accumulator``
       fold (~1,650 rows instead of ~62,300). A unit's contribution has already
       been summed in and cannot be subtracted, so dropping one key from
       ``committed_units`` while keeping the accumulator would DOUBLE-COUNT that
       unit when it re-runs. "Invalidate unit K" has no correct implementation
       here; "invalidate everything" does.
    2. *Resolving the affected ``vm_id`` in-request is not affordable.* The
       ``vm_id`` of a market depends on its group's and event's cardinality
       across the whole eligible population, so it cannot be looked up for 40
       ids in isolation — a filtered roster would compute a group size over the
       filter and return a WRONG ``vm_id``. The canonical unfiltered roster read
       (``_futures_generation_sql``) was measured against production on
       2026-08-14 through the read-only rail: it **exceeded the 10 s statement
       timeout**, inside a request that already budgets 25 s. An approximated
       ``vm_id`` in a report is the invented-fact class this program exists to
       stop, so the tuples are reported as ``(market_id, source)`` with the
       ``vm_id`` named unresolved and the reason attached.

    Discarding the superset is strictly safer than discarding a subset, and the
    cost is bounded: the staged build re-banks its units on the following beats.

    Returns a verdict dict. ``status`` is ``invalidated`` ONLY when the re-read
    proves the cursor is empty — the after-read discipline, because a mutation
    that fails to apply reports green.

    CAL-P062 / C-CERT-1852-R2 specimen one: the STAGED cursor was re-read and the
    MAIN CHECKPOINT was not. Its publish returned ``ok``/``superseded`` and that
    acknowledgement was accepted as proof, so a no-op publisher scored
    ``invalidated`` while the read-identity ledger showed the checkpoint was
    never inspected — and ``superseded``, which is precisely the case where a
    newer checkpoint's banked phases are demonstrably still there, counted as
    success. Both halves are now re-read, and the checkpoint half is judged by
    :func:`~app.utils.calibration_invalidation.main_checkpoint_is_invalidation`
    against the record that is in the store afterwards.
    """
    from app.tasks.calibration_main_build import (
        CHECKPOINT_IDENTITY,
        MAIN_CHECKPOINT_SCHEMA,
        STAGED_FUTURES_IDENTITY,
        save_staged_cursor,
    )
    from app.utils.calibration_staged_futures import (
        STAGED_FUTURES_SCHEMA,
        new_staged_cursor,
    )

    ids = sorted({int(i) for i in market_ids})
    verdict: dict[str, Any] = {
        "status": "not_run",
        "mechanism": "discard staged-futures cursor + main build checkpoint",
        "scope": "WHOLESALE — a superset of the affected units, by necessity",
        "why_not_per_unit": (
            "CAL-P034 folds every banked unit into one accumulator (a unit's "
            "contribution cannot be subtracted), and the canonical roster read "
            "that resolves vm_id exceeded the 10s statement timeout in "
            "production on 2026-08-14."
        ),
        "affected_markets": [],
        "vm_id": "not resolved in-request (see why_not_per_unit)",
    }
    if not ids:
        verdict["status"] = "nothing_written"
        return verdict

    # The (market_id, source) half of the tuple IS cheap and IS exact.
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT id, source FROM futures_markets WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            )
        ).all()
        verdict["affected_markets"] = [
            {"market_id": r.id, "source": r.source} for r in rows
        ]
    except Exception as exc:  # noqa: BLE001 — provenance, never the gate
        verdict["affected_markets_error"] = f"{type(exc).__name__}"

    from app.services.durable_snapshots import read_snapshot_standalone

    async def _banked() -> int | None:
        try:
            read = await read_snapshot_standalone(
                STAGED_FUTURES_IDENTITY,
                expected_version=STAGED_FUTURES_SCHEMA,
                max_age_s=14 * 86400,
            )
        except Exception:  # noqa: BLE001
            return None
        if not read.ok or read.envelope is None:
            return 0 if read.status == "missing" else None
        units = (read.envelope.payload or {}).get("committed_units")
        return len(units) if isinstance(units, list) else None

    before = await _banked()
    verdict["banked_units_before"] = before

    blank = new_staged_cursor(
        population_version="",
        input_fingerprint="",
        generation_fingerprint="",
        owner="repair:kalshi-fabricated-loss",
        generation=0,
    )
    staged_ok = await save_staged_cursor(blank, terminal="invalidated")
    verdict["staged_cursor_write_ok"] = staged_ok

    # The main checkpoint banks whole PHASES, and the futures phase's output is
    # built from futures_outcomes too. Clearing the unit cursor while leaving a
    # banked phase output behind would invalidate the finer state and resume the
    # coarser one — the same mixed generation, one level up.
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.tasks.calibration_main_build import new_main_checkpoint
    from app.utils.durable_state import DurableEnvelope

    try:
        blank_main = new_main_checkpoint(
            version="", fingerprint="", owner="repair:kalshi-fabricated-loss",
            generation=0,
        )
        payload = blank_main.as_payload()
        payload["terminal"] = "invalidated"
        res = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=CHECKPOINT_IDENTITY,
                schema_version=MAIN_CHECKPOINT_SCHEMA,
                payload=payload,
                complete=True,
                source="repair:kalshi-fabricated-loss",
            )
        )
        verdict["main_checkpoint_publish_status"] = res.get("status")
    except Exception as exc:  # noqa: BLE001
        verdict["main_checkpoint_publish_status"] = "raised"
        verdict["checkpoint_error"] = f"{type(exc).__name__}"

    # The publish's own answer is a RESPONSE SHAPE, not a fact about the store.
    # This is the proof, and it is unconditional: it runs even when the publish
    # raised, because the record that matters is the one sitting there now.
    checkpoint_ok, checkpoint_why, checkpoint_read_status = (
        await _main_checkpoint_after_read()
    )
    verdict["main_checkpoint_after_read"] = {
        "read_identity": CHECKPOINT_IDENTITY,
        "read_status": checkpoint_read_status,
        "is_invalidation": checkpoint_ok,
        "why": checkpoint_why,
    }
    verdict["main_checkpoint_write_ok"] = checkpoint_ok

    after = await _banked()
    verdict["banked_units_after"] = after
    verdict["banked_units_discarded"] = (
        before - after if isinstance(before, int) and isinstance(after, int) else None
    )

    if staged_ok and checkpoint_ok and after == 0:
        verdict["status"] = "invalidated"
    else:
        verdict["status"] = "failed"
        verdict["note"] = (
            "The write did not prove itself on re-read. The rows ARE repaired; "
            "the published curve may still resume banked pre-repair units. The "
            "obligation is PERSISTED — re-apply the same plan_hash until this "
            "reads invalidated. Do not run another page until it does."
        )
        verdict["failed_half"] = {
            "staged_cursor": bool(staged_ok),
            "main_checkpoint": bool(checkpoint_ok),
            "staged_after_read_empty": after == 0,
        }
    return verdict


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
    after_id: int | None = None,
    after_date: str | None = None,
    sport: str | None = None,
    plan_hash: str | None = None,
) -> dict[str, Any]:
    """Per-leg retraction/restoration against the venue's own declaration.

    Two halves, and they no longer share a derivation:

    * ``apply=false`` walks one KEYSET page of the population, asks the venue,
      judges per leg through the shipping mapper, and emits a content-addressed
      plan. It writes nothing to ``futures_outcomes``.
    * ``apply=true`` writes ONLY what that plan named, under compare-and-set on
      the exact prior row state the plan recorded, and then invalidates the
      calibration generation. It never re-selects, never re-asks the venue and
      never re-classifies.

    See the module docstring for the contract and
    ``app/utils/kalshi_fabricated_loss.py`` for the judgment.
    """
    started = time.monotonic()

    if offset is not None:
        # Named refusal rather than a silent ignore: an operator draining this
        # rail with the old parameter would otherwise re-read page one forever
        # and call it exhausted.
        return {
            "measured": False,
            "refused": "OFFSET_CURSOR_RETIRED",
            "reason": (
                "?offset= is gone (C-CERT-1852 finding 1): this rail deletes "
                "from its own population, so an offset skips as many untouched "
                "markets as the previous page repaired. Drain with "
                "?after_date=&after_id= from the previous call's next_cursor."
            ),
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    if apply:
        return await _apply_reviewed_plan(session, plan_hash, started)

    return await _dry_run(session, limit, after_id, after_date, sport, started)


async def _dry_run(session, limit, after_id, after_date, sport, started):
    """Select, ask the venue, judge, and emit the reviewed plan. No writes."""
    from app.services.kalshi_api import KalshiAPIService

    window = min(int(limit or APPLY_MARKET_CAP), APPLY_MARKET_CAP)
    if (after_id is None) != (after_date is None):
        return {
            "measured": False,
            "refused": "PARTIAL_CURSOR",
            "reason": (
                "after_date and after_id are ONE position and must be passed "
                "together — half a keyset is a different walk, not a resume."
            ),
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    try:
        await session.execute(
            text(f"SET LOCAL statement_timeout = {_SELECT_TIMEOUT_MS}")
        )
        rows = (
            await session.execute(
                text(_WORK_SQL),
                {
                    "lim": window,
                    "sport": sport,
                    "after_date": after_date,
                    "after_id": after_id,
                },
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
    timed_out = False
    excluded: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    mismatch_samples: list[dict[str, Any]] = []
    planned_legs: list[PlannedLeg] = []
    planned_markets: set[int] = set()

    def _bump(d: dict[str, int], k: str, n: int = 1) -> None:
        d[k] = d.get(k, 0) + n

    service = KalshiAPIService()
    try:
        for row in rows:
            if time.monotonic() - started > _MAX_SECONDS:
                timed_out = True
                break
            if len(planned_markets) >= APPLY_MARKET_CAP:
                # The plan is what the apply will execute, so the cap belongs
                # HERE — capping at write time would emit a plan larger than any
                # apply could honour, and the operator would review a set the
                # rail had already decided to truncate.
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

            legs = await _legs(session, row.market_id)
            judged = plan_market_legs(legs, venue_markets)

            for item in judged:
                _bump(leg_verdicts, item["verdict"])
                if item["verdict"] == "not_at_venue" and len(mismatch_samples) < 12:
                    # Mechanism 2. Recorded so it stops being a sample nobody
                    # reads, and deliberately never written.
                    mismatch_samples.append(
                        {
                            "market_id": row.market_id,
                            "event_ticker": row.event_ticker,
                            "our_ticker": item["external_id"],
                            "venue_legs": len(venue_markets or []),
                        }
                    )
                if item["verdict"] in WRITING_VERDICTS:
                    planned_legs.append(
                        PlannedLeg(
                            leg_id=item["leg_id"],
                            market_id=row.market_id,
                            verdict=item["verdict"],
                            expected_is_winner=item["prior_is_winner"],
                            expected_source=item["prior_source"],
                            external_id=item["external_id"],
                        )
                    )
                    planned_markets.add(row.market_id)
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001
            pass

    cursor = keyset_after(rows, examined)
    plan = build_plan(
        planned_legs,
        context={
            "rail": "kalshi-fabricated-loss",
            "sport": sport,
            "window": window,
            "resumed_from": {"after_date": after_date, "after_id": after_id},
            "next_cursor": cursor,
            "examined": examined,
        },
    )
    plan_ok, plan_note = await _save_plan(plan)

    contract = evaluate_repair_contract(
        candidate_ids=[r.market_id for r in rows],
        processed_ids=[r.market_id for r in rows[:examined]],
        approved_ids=plan.market_ids,
        mutated_ids=[],
        dry_run_ids=None,
        next_cursor=(cursor or {}).get("after_id"),
    )

    return {
        "apply": False,
        "window": {
            "limit": window,
            "returned": len(rows),
            "sport": sport,
            "resumed_from": {"after_date": after_date, "after_id": after_id},
        },
        "examined": examined,
        "market_verdicts": market_verdicts,
        "leg_verdicts": leg_verdicts,
        "markets_would_write": len(plan.market_ids),
        "winners_would_restore": plan.verdict_counts().get("restore_winner", 0),
        "losses_would_retract": plan.verdict_counts().get("retract_fabricated", 0),
        # Ruling 054: an exclusion is a number with a name, never a silent skip.
        "declared_exclusions": excluded,
        "excluded_examples": samples,
        "ticker_mismatch_examples": mismatch_samples,
        # C-CERT-1852 finding 2. THIS is what an apply must present.
        "plan_hash": plan.plan_hash if plan_ok else None,
        "plan_persisted": plan_ok,
        "plan_note": plan_note,
        "plan_leg_ids": list(plan.leg_ids),
        "plan_market_ids": list(plan.market_ids),
        # CAL-P1008: the per-leg VERDICT travels with the response, not only
        # into the one durable slot the next batch overwrites. `plan_leg_ids`
        # above is both arms mixed with no verdict on them, and the restore arm
        # leaves no marker in the row it writes, so without this a drain of more
        # than APPLY_MARKET_CAP markets — i.e. every real drain — cannot say
        # afterwards which legs it flipped, and D51 = B(b)'s "writes a backup
        # first, ships a one-command restore" is unmet from batch two onward.
        # This is the exact payload that was banked, so a captured response
        # re-decodes to this same `plan_hash`: a restorable artifact, not a
        # description of one.
        "plan_artifact": plan.as_payload(),
        "plan_artifact_note": (
            "This IS the backup — capture it per batch BEFORE the next dry-run: "
            f"the durable slot at {PLAN_IDENTITY} holds one plan and batch N+1 "
            "overwrites batch N. Undo the retraction arm by its "
            f"{RETRACTION_SOURCE} marker; undo the restore arm ONLY from the "
            "legs here whose verdict is restore_winner, because that arm writes "
            "api_settlement back over api_settlement and leaves nothing in the "
            "row to find it by."
        ),
        "apply_instruction": (
            f"POST …/kalshi-fabricated-loss?apply=true&plan_hash={plan.plan_hash}"
            if plan_ok
            else "NO PLAN PERSISTED — apply is impossible until a dry-run banks one."
        ),
        # Ruling 050: the operator reads the armed control as part of the plan
        # they are approving, not afterwards in a report.
        "declared_curve_movement": declared_curve_movement(
            winners_restored=plan.verdict_counts().get("restore_winner", 0),
            losses_retracted=plan.verdict_counts().get("retract_fabricated", 0),
        ),
        "next_cursor": cursor,
        "exhausted": (not timed_out) and len(rows) < window,
        "stopped_on_time_budget": timed_out,
        "cursor_contract": contract,
        "elapsed_s": round(time.monotonic() - started, 1),
        "apply_market_cap": APPLY_MARKET_CAP,
        "retraction_source": RETRACTION_SOURCE,
        "prices_touched": False,
        "success": contract["action"] != "REFUSE" and plan_ok,
    }


async def _apply_reviewed_plan(session, plan_hash, started):
    """Execute the reviewed plan, and NOTHING else. Compare-and-set throughout.

    CAL-P062 adds one thing to the sequence, before any row is touched: the
    OBLIGATION LEDGER is read. The apply commits its rows and then invalidates,
    so a failure between those two steps leaves a debt — and C-CERT-1852-R2
    showed that the debt used to die with the HTTP response, after which a retry
    of the same plan drifted on its own committed row, invalidated nothing, and
    reported ``success: true``. The ledger is what a retry retries.

    CAL-P1009-R (CERT-1872) closes the last gap in that: the OPEN debt is STAGED
    IN THE SAME TRANSACTION as the rows, not published after the commit, so the
    interval in which a process loss could take the debt and leave the rows no
    longer exists. See :func:`_stage_obligation`.
    """
    plan, reason = await _load_plan()
    ok, refusals = bind_apply(plan, decode_reason=reason, presented_hash=plan_hash)
    if not ok:
        return {
            "apply": True,
            "measured": False,
            "refused": refusals,
            "decode_reason": reason,
            "presented_plan_hash": plan_hash,
            "artifact_plan_hash": plan.plan_hash if plan is not None else None,
            "reason": (
                "An apply is bound to the dry-run an operator actually read "
                "(C-CERT-1852 finding 2). Run ?apply=false, read the plan, then "
                "pass its plan_hash back."
            ),
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    # --- The outstanding debt, read BEFORE the first write -------------------
    prior, prior_note = await _load_obligation()
    if prior_note not in ("ok", "missing"):
        # UNKNOWN is not "no debt". Writing more rows while unable to read what
        # the last call owes is how the retry specimen compounds.
        return {
            "apply": True,
            "measured": False,
            "refused": ["OBLIGATION_LEDGER_UNREADABLE"],
            "obligation_note": prior_note,
            "reason": (
                "The invalidation obligation ledger could not be read, so this "
                "call cannot tell an unpaid invalidation from none. Nothing was "
                "written."
            ),
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    prior_open = prior is not None and obligation_is_open(prior)
    prior_hash = obligation_plan_hash(prior) if prior_open else None
    prior_owner = prior.get("owner") if prior_open and isinstance(prior, dict) else None
    # CAL-P1009: a debt the RESTORE created is never dischargeable by an apply,
    # not even of its own plan_hash. Re-applying it does pay the curve — by
    # rewriting the very repair the restore undid, which is a decision no
    # retry-shaped call gets to make silently. Both mismatch cases refuse under
    # the same name, and the reason quotes the record instead of assuming it.
    restore_owned = prior_owner == OBLIGATION_OWNER_RESTORE
    if prior_open and (restore_owned or prior_hash != plan.plan_hash):
        return {
            "apply": True,
            "measured": False,
            "refused": ["OUTSTANDING_INVALIDATION"],
            "outstanding_obligation": {
                "plan_hash": prior_hash,
                "market_ids": obligation_market_ids(prior),
                "leg_ids": obligation_leg_ids(prior),
                "owner": prior_owner,
                "discharged_by": obligation_retry_instruction(prior),
            },
            "reason": (
                "A previous "
                + ("restore" if restore_owned else "apply")
                + " committed rows whose calibration invalidation never "
                "discharged, and this call cannot pay that debt: "
                + obligation_retry_instruction(prior)
                + " A new page would compound an unpaid debt against the "
                "published curve."
            ),
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    prior_ids = obligation_market_ids(prior) if prior_open else []
    prior_legs = obligation_leg_ids(prior) if prior_open else []

    # CAL-P1008-R (CERT-965): the undo receipt is banked BEFORE the first UPDATE,
    # at an address only this plan can occupy, and a failure to bank it REFUSES
    # the apply. Ordering is the whole guarantee: banked-then-written can leave a
    # receipt for rows that were never touched (harmless — the restore's
    # compare-and-set finds nothing to reverse), while written-then-banked can
    # leave rows with no receipt at all, which is the state that cannot be
    # recovered from. Re-applying the same plan_hash re-banks the same
    # content-addressed payload, so a retry is idempotent here.
    receipt_ok, receipt_note = await _save_receipt(plan)
    if not receipt_ok:
        return {
            "apply": True,
            "measured": False,
            "refused": ["UNDO_RECEIPT_NOT_BANKED"],
            "receipt_note": receipt_note,
            "receipt_identity": receipt_identity(plan.plan_hash),
            "reason": (
                "The pre-image could not be persisted, so this apply would not "
                "be reversible. NOTHING was written. Retry the same plan_hash "
                "once the durable store answers; the plan is unchanged."
            ),
            "prices_touched": False,
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    index = approved_leg_index(plan)
    written: list[int] = []
    written_legs: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []
    winners_restored = 0
    losses_retracted = 0

    # CAL-P1008-R2 (CERT-970): the apply STAMPS its own version instead of
    # letting the database pick one. `NOW()` would leave the rail unable to say
    # which write produced the row it is looking at, and CERT-970's specimen is
    # exactly a row whose VALUES are the post-apply values but whose write was
    # somebody else's. A value chosen here is known for every row this call
    # writes, without a RETURNING clause, and any later write moves it — so a
    # same-valued concurrent regrade is visible where no state comparison could
    # ever have seen it.
    applied_version = datetime.now(timezone.utc)

    for leg_id in plan.leg_ids:
        item = index[leg_id]
        if item.verdict == "restore_winner":
            # C-CERT-1852 finding 3. The retraction below always carried an
            # exact-source guard; the restore carried only `NOT is_winner`, so a
            # concurrent grader replacing api_settlement with a real result
            # between the plan and the write would have been overwritten by a
            # stale api_settlement. Both forms now compare on the EXACT prior
            # (is_winner, resolution_source) the plan recorded.
            stmt = """
                UPDATE futures_outcomes
                SET is_winner = true,
                    resolution_source = 'api_settlement',
                    last_updated = :applied_version
                WHERE id = :id
                  AND is_winner = :prior_winner
                  AND resolution_source IS NOT DISTINCT FROM :prior_source
            """
            params = {
                "id": leg_id,
                "prior_winner": item.expected_is_winner,
                "prior_source": item.expected_source,
                "applied_version": applied_version,
            }
        else:
            stmt = """
                UPDATE futures_outcomes
                SET resolution_source = :retraction,
                    last_updated = :applied_version
                WHERE id = :id
                  AND is_winner = :prior_winner
                  AND resolution_source IS NOT DISTINCT FROM :prior_source
            """
            params = {
                "id": leg_id,
                "retraction": RETRACTION_SOURCE,
                "prior_winner": item.expected_is_winner,
                "prior_source": item.expected_source,
                "applied_version": applied_version,
            }

        r = await session.execute(text(stmt), params)
        if r.rowcount == 1:
            written.append(leg_id)
            # Only a rowcount of ONE goes in the receipt. That is the whole of
            # CERT-970's fix: a leg the compare-and-set skipped was not written
            # by this call, so nothing may later reverse it as though it were.
            written_legs.append(
                {
                    "leg_id": leg_id,
                    "market_id": item.market_id,
                    "verdict": item.verdict,
                    "prior_is_winner": item.expected_is_winner,
                    "prior_source": item.expected_source,
                    "applied_version": applied_version.isoformat(),
                }
            )
            if item.verdict == "restore_winner":
                winners_restored += 1
            else:
                losses_retracted += 1
        else:
            # Rowcount zero is NOT a no-op to shrug at: the row moved under the
            # plan. Report it by id and skip it — never widen the predicate,
            # never retry without a fresh plan.
            drift.append(
                {
                    "leg_id": leg_id,
                    "market_id": item.market_id,
                    "verdict": item.verdict,
                    "expected_is_winner": item.expected_is_winner,
                    "expected_source": item.expected_source,
                    "rows_affected": r.rowcount,
                    "reason": REASON_CONCURRENT_DRIFT,
                }
            )

    stray = mutations_outside_approved(plan, written)
    if stray:
        # Cannot happen while the loop iterates plan.leg_ids — asserted anyway,
        # because "cannot happen" is what every check-then-act bug said first.
        await session.rollback()
        return {
            "apply": True,
            "measured": False,
            "refused": [REASON_OUTSIDE_APPROVED],
            "stray_leg_ids": stray,
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    # CAL-P1008-R2/R3 (CERT-970, CERT-1858): the record of what was WRITTEN is
    # staged in THIS transaction, before the single commit below. The pre-write
    # plan receipt is the forensic record if the process dies mid-write; THIS
    # one is what a restore binds to, each leg carrying the version the apply
    # stamped. It merges, so a retry adds its legs and an empty write set cannot
    # blank an earlier call's record.
    #
    # The rows and their undo record therefore land together or not at all. If
    # staging fails there is nothing to report honestly about, because nothing
    # was committed.
    applied_ok, applied_note, applied_leg_count = await _stage_applied(
        session, plan.plan_hash, written_legs
    )
    if written and not applied_ok:
        await session.rollback()
        return {
            "apply": True,
            "measured": False,
            "refused": ["UNDO_RECEIPT_NOT_STAGED"],
            "plan_hash": plan.plan_hash,
            "applied_identity": applied_identity(plan.plan_hash),
            "applied_receipt_note": applied_note,
            "legs_written": 0,
            "rolled_back": True,
            "reason": (
                "The record of which rows this apply wrote could not be staged, "
                "so the whole transaction was rolled back and NO row was "
                "changed. Rows without that record cannot be reversed, and an "
                "honest report of an unrecoverable row is not a substitute for "
                "not creating one. Retry the same plan_hash."
            ),
            "prices_touched": False,
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    # --- The debt, staged in the SAME transaction as the rows ----------------
    # CAL-P1009-R (CERT-1872) named this window on the restore; it is the same
    # window here, on the writer that made the ledger necessary in the first
    # place. Committing the rows and only then publishing the OPEN debt leaves
    # an interval in which a process loss takes the debt with it. The union, not
    # this call's `written` set: on a retry the rows are already committed, so
    # `written` is empty and the ledger is the ONLY surviving record of what the
    # curve is owed.
    owed_market_ids = sorted({index[i].market_id for i in written} | set(prior_ids))
    owed_leg_ids = sorted(set(written) | set(prior_legs))
    receipt = (
        new_obligation(
            plan_hash=plan.plan_hash,
            market_ids=owed_market_ids,
            leg_ids=owed_leg_ids,
            owner=OBLIGATION_OWNER_APPLY,
        )
        if written
        else (prior if prior_open else None)
    )

    obligation_persisted, obligation_note = True, "nothing owed"
    if written:
        obligation_persisted, obligation_note = await _stage_obligation(session, receipt)
        if not obligation_persisted:
            await session.rollback()
            return {
                "apply": True,
                "measured": False,
                "refused": ["INVALIDATION_DEBT_NOT_STAGED"],
                "plan_hash": plan.plan_hash,
                "obligation_identity": OBLIGATION_IDENTITY,
                "obligation_note": obligation_note,
                "legs_written": 0,
                "rolled_back": True,
                "reason": (
                    "The invalidation these rows would owe the published curve "
                    "could not be staged, so the whole transaction was rolled "
                    "back and NO row was changed. Rows committed with no durable "
                    "debt can leave the curve stale with nothing naming what "
                    "would pay it. Retry the same plan_hash."
                ),
                "prices_touched": False,
                "success": False,
                "elapsed_s": round(time.monotonic() - started, 1),
            }
        await session.commit()
    elif owed_market_ids:
        # A retry whose rows already landed: it owes nothing NEW and stages
        # nothing. The OPEN record in the slot is the debt, and re-writing it
        # would be a durable write inside a transaction this call never commits.
        obligation_note = "carried forward — the open record in the slot is the debt"

    # Re-READ rather than trust the rowcounts: a mutation that fails to apply
    # reports green, so the proof is the database's own answer.
    after = None
    if written:
        row = (
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
                {"retraction": RETRACTION_SOURCE, "ids": list(plan.market_ids)},
            )
        ).one()
        after = {
            "retracted_now": row.retracted_now,
            "winners_now": row.winners_now,
            "scope": "the markets in THIS plan only",
        }

    invalidation = await invalidate_calibration_generation(session, set(owed_market_ids))

    discharged, discharge_note = invalidation_discharged(
        status=invalidation["status"],
        wrote_rows=bool(written),
        drift_count=len(drift),
        prior_obligation_open=prior_open,
    )

    obligation_cleared = True
    clear_note = "nothing owed"
    if owed_market_ids:
        if discharged:
            obligation_cleared, clear_note = await _save_obligation(
                discharge_obligation(
                    receipt,
                    proof={
                        "staged_after_read": invalidation.get("banked_units_after"),
                        "main_checkpoint_after_read": invalidation.get(
                            "main_checkpoint_after_read"
                        ),
                    },
                )
            )
        else:
            obligation_cleared = False
            clear_note = "left OPEN — the invalidation has not discharged"

    # Every planned leg must have been ATTEMPTED — that is the identity the
    # binding buys, and it is a different claim from "every planned leg was
    # written". A leg the row moved under is attempted, reported and skipped;
    # a leg silently dropped from the loop would be neither, and only this
    # equality can tell the two apart.
    attempted = sorted(written + [d["leg_id"] for d in drift])
    attempted_equals_plan = attempted == list(plan.leg_ids)
    contract = evaluate_repair_contract(
        candidate_ids=list(plan.leg_ids),
        processed_ids=attempted,
        approved_ids=list(plan.leg_ids),
        mutated_ids=written,
        dry_run_ids=None,
        next_cursor=None,
    )

    invalidation_ok = discharged and obligation_persisted and obligation_cleared
    return {
        "apply": True,
        "measured": True,
        "plan_hash": plan.plan_hash,
        "plan_leg_count": len(plan.leg_ids),
        # CAL-P1008-R: the undo, as a command rather than a prose sketch. Banked
        # before the first UPDATE, at an address this batch alone occupies.
        "undo": {
            "receipt_identity": receipt_identity(plan.plan_hash),
            "receipt_banked_before_mutation": True,
            "receipt_note": receipt_note,
            # CAL-P1008-R2: the record a restore actually binds to.
            "applied_identity": applied_identity(plan.plan_hash),
            "applied_receipt_banked": applied_ok,
            "applied_receipt_note": applied_note,
            "applied_leg_count": applied_leg_count,
            "reversible": applied_ok,
            "dry_run": (
                "POST …/repairs/kalshi-fabricated-loss-restore"
                f"?plan_hash={plan.plan_hash}"
            ),
            "apply": (
                "POST …/repairs/kalshi-fabricated-loss-restore"
                f"?apply=true&plan_hash={plan.plan_hash}"
            ),
            "note": (
                "Reverses BOTH arms under compare-and-set on the post-apply row "
                "state, so a row something else has changed since is skipped and "
                "named rather than clobbered. Dry-run by default."
            ),
        },
        "markets_written": len({index[i].market_id for i in written}),
        "legs_written": len(written),
        "winners_restored": winners_restored,
        "losses_retracted": losses_retracted,
        "concurrent_drift": drift,
        "concurrent_drift_count": len(drift),
        "after_reread": after,
        # C-CERT-1852 finding 4: executed, counted, and it GATES success.
        "calibration_invalidation": invalidation,
        "invalidated_units": invalidation.get("banked_units_discarded"),
        # C-CERT-1852-R2 specimen two: the debt, and whether THIS call paid it.
        "invalidation_obligation": {
            "carried_in": {
                "open": prior_open,
                "plan_hash": prior_hash,
                "market_ids": prior_ids,
                "ledger_read": prior_note,
            },
            "owed_market_ids": owed_market_ids,
            "owed_leg_ids": owed_leg_ids,
            # CAL-P1009-R: staged in the same transaction as the rows it is the
            # debt for, not published after them.
            "staged_with_the_rows": bool(written),
            "persisted_before_invalidating": obligation_persisted,
            "persist_note": obligation_note,
            "discharged": discharged,
            "discharge_note": discharge_note,
            "ledger_cleared": obligation_cleared,
            "clear_note": clear_note,
            "state": "discharged" if (obligation_cleared and discharged) else "open",
        },
        # Ruling 050: the prediction travels WITH the write, in the direction
        # CAL-P057 measured — zero on the retraction arm, an ADDITION on restore.
        "declared_curve_movement": declared_curve_movement(
            winners_restored=winners_restored, losses_retracted=losses_retracted
        ),
        "cursor_contract": contract,
        "attempted_leg_ids_equal_plan": attempted_equals_plan,
        "retraction_source": RETRACTION_SOURCE,
        "prices_touched": False,
        "apply_market_cap": APPLY_MARKET_CAP,
        "next_cursor": (plan.context or {}).get("next_cursor"),
        "success": (
            invalidation_ok
            and attempted_equals_plan
            and contract["action"] != "REFUSE"
            # CAL-P1008-R2: rows committed with no applied receipt are rows
            # nothing can reverse. That is a debt like the invalidation's, and
            # it is reported as failure rather than left to be noticed.
            and (applied_ok or not written)
        ),
        "success_note": (
            "success is FALSE unless the calibration invalidation executed and "
            "proved itself on re-read of BOTH the staged cursor and the main "
            "checkpoint, and unless the obligation this call carried is "
            "recorded discharged. `nothing_written` is a discharge only for a "
            "plan proven never to have written — never for one whose legs "
            "drifted, and never for one carrying an open debt. Rows may be "
            "repaired while success is false; that is the honest state, not a "
            "contradiction."
        ),
        "elapsed_s": round(time.monotonic() - started, 1),
    }


# ---------------------------------------------------------------------------
# THE RESTORE (CAL-P1008-R, CERT-965): the undo, as a command that runs
# ---------------------------------------------------------------------------


async def restore(
    session,
    apply: bool = False,
    plan_hash: str | None = None,
) -> dict[str, Any]:
    """Reverse one applied batch, from its banked receipt. Dry-run by default.

        POST /api/admin/repairs/kalshi-fabricated-loss-restore?plan_hash=<hash>
        POST …?apply=true&plan_hash=<hash>

    CERT-965's required repair, corrected by CERT-970. Four properties:

    1. **It is bound to what was WRITTEN, not to what was planned.** CERT-970's
       specimen: a concurrent grader moves a planned leg to ``(true,
       api_settlement)`` — the same state a successful apply produces — so the
       apply's compare-and-set skips it as drift and never writes it. A restore
       driven off the PLAN would then find its post-apply predicate satisfied
       and set ``is_winner`` back to false, destroying a real grade. So the
       binding is :func:`applied_identity`, whose legs are exactly the rowcount-1
       writes. The pre-write plan receipt stays, as the forensic record if a
       process dies mid-write; it never drives a write.
    2. **Every arm also compares on the version the apply STAMPED.** Values are
       not enough — a same-valued regrade after a successful apply leaves a row
       whose state is identical and whose grade is somebody else's. Each write
       carries ``last_updated = :applied_version``, a value the apply chose, and
       the restore requires it. Any later write to the row, of any value, moves
       it and the restore declines.
    3. **It re-derives nothing.** No venue call, no classification, no work SQL
       — the same discipline ``apply=true`` is held to, for the same reason.
    4. **A row that has moved is reported by id and skipped.** Never widened,
       never retried without a fresh receipt.
    5. **It joins the invalidation obligation ledger** (CAL-P1009). A restore
       moves grades, so it owes the published curve an invalidation exactly as
       an apply does — and it writes the same one durable slot. Before it
       reverses anything it reads the ledger and refuses if the read is UNKNOWN;
       its own OPEN debt is STAGED IN THE TRANSACTION THAT REVERSES THE ROWS
       (CAL-P1009-R, CERT-1872 — banking it after the commit left a window in
       which a process loss took the debt and left the curve stale), carrying
       any prior debt's ids forward in the union so the slot never drops one;
       and it discharges only on the proved invalidation. The record says a
       RESTORE discharges it: the previous shape would have told an operator to
       re-apply the plan, which pays the curve by redoing the repair the restore
       had just undone.

    The dry-run tells you what it would touch without touching it. It reads the
    receipt and reports, and it deliberately does NOT pre-check the rows: a
    prediction made from a read that the write does not repeat is the stale-read
    clobber this rail already fixed once.
    """
    started = time.monotonic()

    if not plan_hash:
        return {
            "restore": True,
            "measured": False,
            "refused": ["PLAN_HASH_REQUIRED"],
            "reason": (
                "A restore is bound to ONE applied batch. Pass the plan_hash the "
                "apply returned (it is in that response's `undo` block)."
            ),
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    legs, reason = await _load_applied(plan_hash)
    if legs is None:
        return {
            "restore": True,
            "measured": False,
            "refused": [reason],
            "presented_plan_hash": plan_hash,
            "applied_identity": applied_identity(plan_hash),
            "plan_receipt_identity": receipt_identity(plan_hash),
            "reason": (
                "No trustworthy record of what that apply WROTE. A receipt that "
                "cannot be read is NOT a batch with nothing to undo (gotcha #53), "
                "and the pre-write plan receipt is deliberately not a substitute "
                "(CERT-970): it names legs the apply may have skipped, and "
                "reversing one of those destroys somebody else's grade. Refuses "
                "rather than reporting a clean zero. The plan receipt is still at "
                "the address above, for a human to read."
            ),
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    index = {leg["leg_id"]: leg for leg in legs}
    by_arm: dict[str, int] = {}
    for leg in legs:
        by_arm[leg["verdict"]] = by_arm.get(leg["verdict"], 0) + 1

    if not apply:
        return {
            "restore": True,
            "apply": False,
            "measured": True,
            "plan_hash": plan_hash,
            "applied_identity": applied_identity(plan_hash),
            "legs_would_reverse": len(legs),
            "by_arm": by_arm,
            "leg_ids": sorted(index),
            "market_ids": sorted({leg["market_id"] for leg in legs}),
            "bound_to": (
                "the rows this apply WROTE (rowcount 1), each pinned to the "
                "last_updated value the apply stamped — not the plan"
            ),
            "restores_to": {
                "restore_winner": "is_winner ← the prior value the apply recorded",
                "retract_fabricated": "resolution_source ← the prior value the apply recorded",
            },
            "declared_curve_movement": declared_curve_movement(
                # The mirror image of the apply's prediction: reversing a
                # restored winner REMOVES it, reversing a retraction RETURNS a
                # leg to the published curve.
                winners_restored=-by_arm.get("restore_winner", 0),
                losses_retracted=-by_arm.get("retract_fabricated", 0),
            ),
            "apply_instruction": (
                f"POST …/kalshi-fabricated-loss-restore?apply=true&plan_hash={plan_hash}"
            ),
            "prices_touched": False,
            "success": True,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    # --- The outstanding debt, read BEFORE the first write -------------------
    # CAL-P1009. The obligation ledger is ONE slot and the apply already writes
    # it, so a restore that reversed rows and then banked its own debt without
    # reading first would ERASE an apply's unpaid invalidation — the single-slot
    # hazard, on the recovery path. Reading first lets this call carry that debt
    # forward in its own record instead of overwriting it. UNKNOWN is not "no
    # debt": reversing rows while unable to read what is owed is how the union
    # loses an id.
    prior, prior_note = await _load_obligation()
    if prior_note not in ("ok", "missing"):
        return {
            "restore": True,
            "apply": True,
            "measured": False,
            "refused": ["OBLIGATION_LEDGER_UNREADABLE"],
            "obligation_note": prior_note,
            "presented_plan_hash": plan_hash,
            "reason": (
                "The invalidation obligation ledger could not be read, so this "
                "restore cannot tell an unpaid invalidation from none — and its "
                "own debt would land in the same slot. Nothing was written."
            ),
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }
    prior_open = prior is not None and obligation_is_open(prior)
    prior_ids = obligation_market_ids(prior) if prior_open else []
    prior_legs = obligation_leg_ids(prior) if prior_open else []

    reversed_ids: list[int] = []
    drift: list[dict[str, Any]] = []
    winners_unrestored = 0
    retractions_undone = 0
    restored_version = datetime.now(timezone.utc)

    for leg_id in sorted(index):
        item = index[leg_id]
        # The version is stored as text and BOUND AS A DATETIME. asyncpg types
        # its binds, so a string against a timestamptz column is a driver error,
        # not an implicit cast — and a version we cannot parse is a leg we cannot
        # prove we wrote, which is a refusal rather than a widened predicate.
        try:
            applied_version = datetime.fromisoformat(item["applied_version"])
        except (TypeError, ValueError):
            drift.append(
                {
                    "leg_id": leg_id,
                    "market_id": item["market_id"],
                    "verdict": item["verdict"],
                    "rows_affected": None,
                    "note": (
                        "the receipt's applied_version is unparseable, so this "
                        "leg cannot be pinned to the write that produced it. "
                        "Left alone."
                    ),
                }
            )
            continue
        if item["verdict"] == "restore_winner":
            # The apply set (true, api_settlement) and wrote api_settlement back
            # over itself, so the post-apply VALUES carry no marker. The version
            # the apply stamped is the marker, and it is the clause that makes
            # this safe against CERT-970's same-valued concurrent write.
            stmt = """
                UPDATE futures_outcomes
                SET is_winner = :prior_winner,
                    last_updated = :restored_version
                WHERE id = :id
                  AND is_winner = true
                  AND resolution_source IS NOT DISTINCT FROM :repairable
                  AND last_updated = :applied_version
            """
            params = {
                "id": leg_id,
                "prior_winner": item["prior_is_winner"],
                "repairable": REPAIRABLE_SOURCE,
                "applied_version": applied_version,
                "restored_version": restored_version,
            }
        else:
            stmt = """
                UPDATE futures_outcomes
                SET resolution_source = :prior_source,
                    last_updated = :restored_version
                WHERE id = :id
                  AND is_winner = :prior_winner
                  AND resolution_source IS NOT DISTINCT FROM :retraction
                  AND last_updated = :applied_version
            """
            params = {
                "id": leg_id,
                "prior_source": item["prior_source"],
                "prior_winner": item["prior_is_winner"],
                "retraction": RETRACTION_SOURCE,
                "applied_version": applied_version,
                "restored_version": restored_version,
            }

        r = await session.execute(text(stmt), params)
        if r.rowcount == 1:
            reversed_ids.append(leg_id)
            if item["verdict"] == "restore_winner":
                winners_unrestored += 1
            else:
                retractions_undone += 1
        else:
            drift.append(
                {
                    "leg_id": leg_id,
                    "market_id": item["market_id"],
                    "verdict": item["verdict"],
                    "rows_affected": r.rowcount,
                    "note": (
                        "no longer the row this apply left — something has "
                        "written it since, which includes a regrade to the same "
                        "values. Left alone."
                    ),
                }
            )

    stray = sorted(set(reversed_ids) - set(index))
    if stray:
        await session.rollback()
        return {
            "restore": True,
            "apply": True,
            "measured": False,
            "refused": [REASON_OUTSIDE_APPROVED],
            "stray_leg_ids": stray,
            "success": False,
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    # --- The debt, staged in the SAME transaction as the reversals -----------
    # CAL-P1009-R (CERT-1872). Recording it after the commit was still a hole:
    # committing the reversed rows and only then publishing the OPEN debt leaves
    # an interval in which a process loss takes the debt with it, and what
    # survives is a stale published curve with no durable retry handle. So the
    # debt rides the reversal's own transaction — both, or neither.
    #
    # The union carries any prior open debt forward. Invalidation here is
    # WHOLESALE by construction (it discards the staged cursor and the main
    # checkpoint outright), so one proved invalidation genuinely pays every id
    # in the union, and the one slot never drops one.
    touched_markets = sorted({index[i]["market_id"] for i in reversed_ids})
    owed_market_ids = sorted(set(touched_markets) | set(prior_ids))
    owed_leg_ids = sorted(set(reversed_ids) | set(prior_legs))
    receipt = (
        new_obligation(
            plan_hash=plan_hash,
            market_ids=owed_market_ids,
            leg_ids=owed_leg_ids,
            owner=OBLIGATION_OWNER_RESTORE,
            retry_instruction=RESTORE_DISCHARGES,
        )
        if reversed_ids
        else (prior if prior_open else None)
    )

    obligation_persisted, obligation_note = True, "nothing owed"
    if reversed_ids:
        obligation_persisted, obligation_note = await _stage_obligation(session, receipt)
        if not obligation_persisted:
            await session.rollback()
            return {
                "restore": True,
                "apply": True,
                "measured": False,
                "refused": ["INVALIDATION_DEBT_NOT_STAGED"],
                "plan_hash": plan_hash,
                "obligation_identity": OBLIGATION_IDENTITY,
                "obligation_note": obligation_note,
                "legs_reversed": 0,
                "rolled_back": True,
                "reason": (
                    "The invalidation these reversals would owe the published "
                    "curve could not be staged, so the whole transaction was "
                    "rolled back and NO row was reversed. Reversed rows whose "
                    "debt is not durable can leave the curve stale with nothing "
                    "naming what would pay it, and reporting that state honestly "
                    "is not a substitute for not creating it. Retry the same "
                    "plan_hash."
                ),
                "prices_touched": False,
                "success": False,
                "elapsed_s": round(time.monotonic() - started, 1),
            }
        await session.commit()
    elif owed_market_ids:
        # Nothing left to reverse, so this call owes nothing NEW and stages
        # nothing: the OPEN record already in the slot IS the debt, and
        # re-writing it would be a durable write inside a transaction this call
        # never commits. This is the retry the ledger exists for — the ids come
        # from that record and the invalidation below is what pays them.
        obligation_note = "carried forward — the open record in the slot is the debt"

    # Same discipline as the apply: the curve is invalidated and the
    # invalidation is PROVED, not declared. A restore moves grades, so a banked
    # unit computed from the repaired rows is as wrong as one computed from the
    # unrepaired rows would have been.
    invalidation = await invalidate_calibration_generation(session, set(owed_market_ids))
    discharged, discharge_note = invalidation_discharged(
        status=invalidation["status"],
        wrote_rows=bool(reversed_ids),
        drift_count=len(drift),
        prior_obligation_open=prior_open,
    )

    obligation_cleared = True
    clear_note = "nothing owed"
    if owed_market_ids:
        if discharged:
            obligation_cleared, clear_note = await _save_obligation(
                discharge_obligation(
                    receipt,
                    proof={
                        "staged_after_read": invalidation.get("banked_units_after"),
                        "main_checkpoint_after_read": invalidation.get(
                            "main_checkpoint_after_read"
                        ),
                    },
                )
            )
        else:
            obligation_cleared = False
            clear_note = "left OPEN — the invalidation has not discharged"

    attempted = sorted(reversed_ids + [d["leg_id"] for d in drift])
    attempted_equals_receipt = attempted == sorted(index)
    contract = evaluate_repair_contract(
        candidate_ids=sorted(index),
        processed_ids=attempted,
        approved_ids=sorted(index),
        mutated_ids=reversed_ids,
        dry_run_ids=None,
        next_cursor=None,
    )

    return {
        "restore": True,
        "apply": True,
        "measured": True,
        "plan_hash": plan_hash,
        "applied_identity": applied_identity(plan_hash),
        "legs_reversed": len(reversed_ids),
        "reversed_leg_ids": reversed_ids,
        "winners_unrestored": winners_unrestored,
        "retractions_undone": retractions_undone,
        "concurrent_drift": drift,
        "concurrent_drift_count": len(drift),
        "calibration_invalidation": invalidation,
        "invalidation_discharged": discharged,
        "invalidation_note": discharge_note,
        # CAL-P1009: the restore's own debt, in the ledger the apply reads.
        "invalidation_obligation": {
            "identity": OBLIGATION_IDENTITY,
            "owner": (receipt or {}).get("owner", OBLIGATION_OWNER_RESTORE),
            "carried_prior_debt": bool(prior_ids or prior_legs),
            "prior_obligation_open": prior_open,
            "market_ids": owed_market_ids,
            "leg_ids": owed_leg_ids,
            # CAL-P1009-R: not "persisted, afterwards" — staged in the same
            # transaction as the rows it is the debt for.
            "staged_with_the_reversals": bool(reversed_ids),
            "persisted_before_invalidating": obligation_persisted,
            "persist_note": obligation_note,
            "discharged": obligation_cleared,
            "discharge_note": clear_note,
            "discharged_by": obligation_retry_instruction(receipt),
        },
        "declared_curve_movement": declared_curve_movement(
            winners_restored=-winners_unrestored, losses_retracted=-retractions_undone
        ),
        "attempted_leg_ids_equal_receipt": attempted_equals_receipt,
        "cursor_contract": contract,
        "prices_touched": False,
        "success": (
            discharged
            and obligation_persisted
            and obligation_cleared
            and attempted_equals_receipt
            and contract["action"] != "REFUSE"
        ),
        "success_note": (
            "success is FALSE unless every leg the receipt names was ATTEMPTED, "
            "the calibration invalidation proved itself, and this restore's own "
            "obligation was banked and then discharged. Rows may be reversed "
            "while success is false; drift is reported, never hidden."
        ),
        "elapsed_s": round(time.monotonic() - started, 1),
    }
