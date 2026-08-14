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
from typing import Any

from sqlalchemy import text

from app.utils.kalshi_fabricated_loss import (
    POPULATION_HAVING_SQL,
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
    APPLY_PLAN_SCHEMA,
    REASON_CONCURRENT_DRIFT,
    REASON_OUTSIDE_APPROVED,
    PlannedLeg,
    approved_leg_index,
    bind_apply,
    build_plan,
    decode_plan,
    evaluate_repair_contract,
    keyset_after,
    mutations_outside_approved,
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
      AND (:sport IS NULL OR fm.llm_sport_category = :sport)
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
        return None, f"plan read raised: {type(exc).__name__}"
    if not read.ok or read.envelope is None:
        return None, f"plan artifact unreadable: {read.status}"
    return decode_plan(read.envelope.payload)


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
        checkpoint_ok = res.get("status") in ("ok", "superseded")
    except Exception as exc:  # noqa: BLE001
        checkpoint_ok = False
        verdict["checkpoint_error"] = f"{type(exc).__name__}"
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
            "the published curve may still resume banked pre-repair units. Do "
            "not run another page until this is cleared."
        )
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
    """Execute the reviewed plan, and NOTHING else. Compare-and-set throughout."""
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

    index = approved_leg_index(plan)
    written: list[int] = []
    drift: list[dict[str, Any]] = []
    winners_restored = 0
    losses_retracted = 0

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
                    last_updated = NOW()
                WHERE id = :id
                  AND is_winner = :prior_winner
                  AND resolution_source IS NOT DISTINCT FROM :prior_source
            """
            params = {
                "id": leg_id,
                "prior_winner": item.expected_is_winner,
                "prior_source": item.expected_source,
            }
        else:
            stmt = """
                UPDATE futures_outcomes
                SET resolution_source = :retraction,
                    last_updated = NOW()
                WHERE id = :id
                  AND is_winner = :prior_winner
                  AND resolution_source IS NOT DISTINCT FROM :prior_source
            """
            params = {
                "id": leg_id,
                "retraction": RETRACTION_SOURCE,
                "prior_winner": item.expected_is_winner,
                "prior_source": item.expected_source,
            }

        r = await session.execute(text(stmt), params)
        if r.rowcount == 1:
            written.append(leg_id)
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

    if written:
        await session.commit()

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

    invalidation = await invalidate_calibration_generation(
        session, {index[i].market_id for i in written}
    )

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

    invalidation_ok = invalidation["status"] in ("invalidated", "nothing_written")
    return {
        "apply": True,
        "measured": True,
        "plan_hash": plan.plan_hash,
        "plan_leg_count": len(plan.leg_ids),
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
        ),
        "success_note": (
            "success is FALSE unless the calibration invalidation executed and "
            "proved itself on re-read. Rows may be repaired while success is "
            "false; that is the honest state, not a contradiction."
        ),
        "elapsed_s": round(time.monotonic() - started, 1),
    }
