"""Grade the 25,264 Polymarket markets nobody ever graded — #1912's backward repair.

CAL-P065. The forward fix (this queue, ``app/utils/pm_market_ownership.py``)
closed the ownership hole so the debt is visible and both rails read NOT-GREEN.
This is the rail for the rows already sitting ungraded.

WHAT THE CENSUS ESTABLISHED, so nobody re-derives it. Of 29,089 zero-winner
Polymarket tennis markets, **25,264 (86.9%) have ``resolution_source`` NULL on
every leg** — their ``is_winner = false`` is the COLUMN DEFAULT standing in for
a grade that was never written, not a verdict that they lost. All resolved in
2026, all inside Polymarket retention (re-probed, exit 0), zero evidence-absent.
And that is tennis alone.

The split is the whole finding, and it is gotcha #53 turned on our own writer:

* ``is_winner=false`` + ``resolution_source`` NULL — nothing ever decided this.
* ``is_winner=false`` + a NAMED source on every leg — something ran, looked,
  and actively wrote "loser" on all sides. A wrong answer, not a missing one.

A bare zero-winner count cannot tell them apart and they need OPPOSITE fixes.
This rail addresses only the first, and its cohort predicate says so:
``bool_and(fo.resolution_source IS NULL)`` — every leg source-less, so a
partially-graded market is left to the authority ladder rather than half
rewritten here.

WHY THIS IS AN ATTENDED APPLY AND NOT A BEAT
--------------------------------------------
25,264 markets is not a thing a scheduled task should decide to do. The rail is
the repairs-as-endpoints pattern (gotcha #48 — a repair is an endpoint that
returns its own census, never an incantation), bound to a reviewed plan:

    POST /api/admin/repairs/pm-never-graded-census           # never writes
    POST /api/admin/repairs/pm-never-graded?apply=false      # dry-run + plan
    ...returns ``plan_hash`` and persists the plan artifact
    POST /api/admin/repairs/pm-never-graded?apply=true&plan_hash=<hash>

``apply=true`` re-derives NOTHING: it loads the content-addressed artifact the
dry-run wrote, refuses unless the operator's ``plan_hash`` matches the
artifact's own re-derived address, and writes ONLY the leg ids that plan names.
No venue call, no classification, no work SQL at apply time. Every refusal has
a name (``app/utils/repair_apply_plan.py``).

INHERITED BY PATTERN, NOT BY ACCIDENT (CAL-P062 / C-CERT-1852-R2)
-----------------------------------------------------------------
This is a WRITER, so it carries the obligation ledger:

* the apply commits its rows BEFORE invalidating the calibration generation, so
  a failed invalidation is a DEBT — persisted at :data:`OBLIGATION_IDENTITY`
  before the invalidation is attempted, not discovered afterwards;
* a retry retries THAT obligation's market ids, because on the retry the rows
  are already committed and ``written`` is empty — the ledger is the only
  surviving record of what must be invalidated;
* ``success: false`` with ``legs_written > 0`` is an HONEST state. **Retry the
  same ``plan_hash``. Do not re-plan.**

WAVE RULE (ruling 046, restated for CAL-P065): one apply per read, never two
applies between reads. This repair joins the wave with its OWN read — its
effect on the published curve must be measurable against a generation that
contains no other apply.

WHAT THIS DOES NOT TOUCH: prices. ``calibration_probability``,
``current_probability`` and the ``opening_*`` family are left exactly as they
are. This repair supplies a missing verdict about an OUTCOME; inventing a price
to go with it would be the same class of error one layer down.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text

from app.utils.calibration_invalidation import (
    INVALIDATION_OBLIGATION_SCHEMA,
    discharge_obligation,
    invalidation_discharged,
    new_obligation,
    obligation_is_open,
    obligation_leg_ids,
    obligation_market_ids,
    obligation_plan_hash,
)
from app.utils.repair_apply_plan import (
    APPLY_PLAN_SCHEMA,
    REASON_CONCURRENT_DRIFT,
    PlannedLeg,
    approved_leg_index,
    bind_apply,
    build_plan,
    decode_plan,
    evaluate_repair_contract,
    mutations_outside_approved,
)

logger = logging.getLogger(__name__)

#: The write source. DISTINCT, so this entire cohort is revertible in ONE
#: predicate without also reverting #989's `clob_authoritative` cohort or the
#: `clob_ordinal` tier. Already registered tier-3 / calibration-truth-eligible
#: (`app/utils/resolution_authority.py`) — it was declared by CAL-P003 and has
#: been waiting for a write path ever since.
WRITE_SOURCE = "clob_never_graded"

#: Hard ceiling on markets written per call. A module constant, NOT a parameter,
#: so "capped" cannot be dialled off mid-run (the winner-field-repair
#: discipline). 25,264 markets is ~632 attended calls, and that is the point:
#: an operator sees a census between every one of them.
APPLY_MARKET_CAP = 40

#: TOTAL wall-clock budget measured from entry, not a per-phase budget — the
#: web dyno's 30s HTTP wall does not care which phase spent it. A partial page
#: with a resume cursor is a NORMAL outcome and says so.
_MAX_SECONDS = 25.0

#: Statement budget for the census. On expiry the count is ABSENT with a reason
#: (``measured: false``), never a clean zero — gotcha #54. The whole argument
#: for this repair rests on a population size, so a census that dies must not
#: be able to report a comfortable one.
_CENSUS_TIMEOUT_MS = 20_000

#: One slot. A dry-run overwrites it, and the content address is what stops an
#: operator applying the page they read two pages ago.
PLAN_IDENTITY = "calibration:repair:pm_never_graded:plan"
OBLIGATION_IDENTITY = "calibration:repair:pm_never_graded:invalidation_obligation"

#: A debt must never age out of visibility: an expiry reads as UNREADABLE
#: (which refuses) rather than as absence (which would let the next apply run).
_OBLIGATION_MAX_AGE_S = 365 * 86400

_OWNER = "repair:pm-never-graded"


# ---------------------------------------------------------------------------
# Population
# ---------------------------------------------------------------------------

#: The never-graded cohort, shared by the census and the work selection so they
#: can never disagree about who is in it. Mirrors
#: ``clob_resolve._cohort_having(_COHORT_NEVER_GRADED)`` — the same predicate
#: the drain now reaches, because two definitions of one cohort is how a repair
#: ends up writing to rows its census never counted.
POPULATION_HAVING_SQL = (
    "HAVING bool_or(fo.is_winner) IS NOT TRUE\n"
    "   AND bool_and(fo.resolution_source IS NULL)"
)

_CENSUS_SQL = f"""
    SELECT COALESCE(fm.llm_sport_category, 'unknown') AS category,
           count(*) AS markets
    FROM (
        SELECT fm.id, fm.llm_sport_category
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
          AND fm.external_id LIKE '0x%'
        GROUP BY fm.id, fm.llm_sport_category
        {POPULATION_HAVING_SQL}
    ) fm
    GROUP BY 1
    ORDER BY 2 DESC
"""


async def census(session, apply: bool = False) -> dict[str, Any]:
    """Size the WHOLE never-graded Polymarket population. Never writes.

    ``apply`` is accepted and IGNORED — the dispatcher passes it positionally
    to every repair, and a census that could be switched into a writer by a
    query parameter is not a census.

    Deliberately grouped by category and not filtered to tennis. The 25,264
    figure is tennis alone, and the queue's own scope note says so: promising a
    drain rate against a population nobody has sized is how a rail gets
    scheduled at 1,200 checks/day against a five-figure backlog.
    """
    started = time.monotonic()
    try:
        await session.execute(
            text(f"SET LOCAL statement_timeout = {_CENSUS_TIMEOUT_MS}")
        )
        rows = (await session.execute(text(_CENSUS_SQL))).all()
    except Exception as exc:  # noqa: BLE001
        try:
            await session.rollback()
        except Exception:
            pass
        return {
            "measured": False,
            "reason": f"census_timeout_or_error: {str(exc)[:160]}",
            "elapsed_s": round(time.monotonic() - started, 2),
            "note": (
                "An unbounded query that dies is an ABSENT measurement, never a "
                "clean zero (gotcha #54). Shard by category and retry."
            ),
        }
    by_category = {r.category: int(r.markets) for r in rows}
    return {
        "measured": True,
        "total_markets": sum(by_category.values()),
        "by_category": by_category,
        "cohort": "resolution_source IS NULL on EVERY leg, no winner crowned",
        "write_source_if_applied": WRITE_SOURCE,
        "elapsed_s": round(time.monotonic() - started, 2),
    }


# ---------------------------------------------------------------------------
# Plan + obligation persistence (CAL-P058 / CAL-P062 pattern)
# ---------------------------------------------------------------------------


async def _save_plan(plan) -> tuple[bool, str]:
    """Persist the dry-run's plan. A failure is REPORTED, never swallowed — an
    operator who cannot be handed a plan hash must be told so, because the next
    thing they will do is try to apply."""
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PLAN_IDENTITY,
                schema_version=APPLY_PLAN_SCHEMA,
                payload=plan.as_payload(),
                complete=True,
                source=_OWNER,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"plan persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"plan persist rejected: {result.get('status')}"


async def _load_plan():
    """``(plan, reason)`` — re-digested from its own content, never believed."""
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


async def _load_obligation() -> tuple[dict[str, Any] | None, str]:
    """``(record, note)``. ``missing`` means no debt; anything other than
    ``missing``/``ok`` is UNKNOWN and the caller must REFUSE, never read it as
    an absence of debt."""
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
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=OBLIGATION_IDENTITY,
                schema_version=INVALIDATION_OBLIGATION_SCHEMA,
                payload=record,
                complete=True,
                source=_OWNER,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"obligation persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"obligation persist rejected: {result.get('status')}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    plan_hash: str | None = None,
) -> dict[str, Any]:
    """Dry-run (build a plan) or apply (execute a reviewed one). Never both.

    Signature ordered to match the dispatcher in ``routes/admin_repairs.py``,
    which calls ``fn(db, apply, **extra)`` — ``apply`` is POSITIONAL there, and
    a keyword-only parameter would have made this repair permanently
    un-appliable while looking correct in isolation.
    """
    started = time.monotonic()
    if apply:
        return await _apply_reviewed_plan(session, plan_hash, started)
    return await _dry_run(
        session, min(limit or APPLY_MARKET_CAP, APPLY_MARKET_CAP), started
    )


async def _dry_run(session, limit: int, started: float) -> dict[str, Any]:
    """Venue-verify a bounded page and emit the plan. WRITES NOTHING.

    The venue answer is the ONLY thing that may crown an outcome here. The
    cohort is defined by the ABSENCE of a grade, so there is nothing local to
    infer from — and inferring one from a price is the gotcha #21 move that
    produced the mis-graded cohort this rail's sibling exists to retract.
    """
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.clob_resolve import (
        _COHORT_NEVER_GRADED,
        _DEFAULT_WRITE_TIERS,
        _fetch_and_map,
        _load_cohort,
        _load_outcomes,
    )

    rows = await _load_cohort(session, limit, None, cohort=_COHORT_NEVER_GRADED)
    outcomes_by_market = await _load_outcomes(session, [r.id for r in rows])

    service = PolymarketAPIService()
    verdicts: dict[str, int] = {}
    planned: list[PlannedLeg] = []
    examined: list[int] = []
    excluded: list[dict[str, Any]] = []
    try:
        for r in rows:
            if time.monotonic() - started > _MAX_SECONDS:
                break
            examined.append(r.id)
            res = await _fetch_and_map(service, r, outcomes_by_market)

            # RULING 054 — exclusions are COUNTED, not skipped. Every market
            # this rail cannot repair leaves with a NAMED verdict and a number.
            if res.get("error"):
                verdict = "venue_lookup_failed"   # gotcha #36: not an absence
            elif res.get("not_found"):
                verdict = "not_at_venue"
            elif not res.get("integrity_ok", True):
                verdict = "integrity_refused"
            elif res.get("skip"):
                verdict = str(res["skip"])
            elif res.get("tier") not in _DEFAULT_WRITE_TIERS:
                verdict = str(res.get("tier") or "unclassified")
            else:
                verdict = str(res["tier"])

            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            if verdict not in _DEFAULT_WRITE_TIERS:
                excluded.append({"market_id": r.id, "verdict": verdict,
                                 "market": res.get("market")})
                continue

            legs = outcomes_by_market.get(r.id, [])
            by_id = {leg["id"]: leg for leg in legs}
            for leg_id, wins in ((res["winner_id"], True), (res["loser_id"], False)):
                leg = by_id.get(leg_id)
                if leg is None:
                    continue
                planned.append(
                    PlannedLeg(
                        leg_id=int(leg_id),
                        market_id=int(r.id),
                        verdict="winner" if wins else "loser",
                        # The cohort's DEFINING property, carried as the
                        # compare half of the compare-and-set: every leg was
                        # source-less and un-crowned when we read it. If that
                        # is no longer true at apply time, something else
                        # graded this market and we must not overwrite it.
                        expected_is_winner=False,
                        expected_source=None,
                        external_id=leg.get("external_id"),
                    )
                )
    finally:
        await service.close()

    plan = build_plan(
        planned,
        context={
            "owner": _OWNER,
            "cohort": "pm_never_graded",
            "write_source": WRITE_SOURCE,
            "examined_markets": len(examined),
            "verdicts": verdicts,
            "issue": 1912,
        },
    )
    plan_ok, plan_note = await _save_plan(plan) if planned else (False, "nothing to plan")

    return {
        "mode": "dry_run",
        "wrote": False,
        "examined_markets": len(examined),
        "planned_markets": len(plan.market_ids),
        "planned_legs": len(plan.legs),
        "verdicts": verdicts,
        "excluded_sample": excluded[:10],
        "plan_persisted": plan_ok,
        "plan_note": plan_note,
        "plan_hash": plan.plan_hash if plan_ok else None,
        "elapsed_s": round(time.monotonic() - started, 2),
        "next": (
            f"POST …/pm-never-graded?apply=true&plan_hash={plan.plan_hash}"
            if plan_ok else
            "NOT APPLIABLE — the plan was not persisted; re-run the dry-run."
        ),
        "wave_rule": (
            "Ruling 046: one apply per read. This repair joins the wave with "
            "its OWN read — do not land it alongside another apply, or neither "
            "one's curve movement can be attributed."
        ),
    }


async def _apply_reviewed_plan(session, plan_hash, started) -> dict[str, Any]:
    """Execute EXACTLY the reviewed plan. Re-derives nothing."""
    plan, decode_reason = await _load_plan()
    ok, refusals = bind_apply(plan, decode_reason=decode_reason, presented_hash=plan_hash)
    if not ok:
        return {
            "mode": "apply",
            "wrote": False,
            "success": False,
            "refused": refusals,
            "presented_plan_hash": plan_hash,
            "artifact_plan_hash": plan.plan_hash if plan is not None else None,
            "note": "Run the dry-run and pass ITS plan_hash back.",
        }

    prior, prior_note = await _load_obligation()
    if prior_note not in ("missing", "ok"):
        return {
            "mode": "apply", "wrote": False, "success": False,
            "refused": ["OBLIGATION_LEDGER_UNREADABLE"],
            "note": (
                f"{prior_note} — an unreadable debt ledger is not an absence of "
                "debt. Refusing rather than risking a second uninvalidated write."
            ),
        }
    prior_open = prior is not None and obligation_is_open(prior)
    prior_hash = obligation_plan_hash(prior) if prior_open else None
    if prior_open and prior_hash != plan.plan_hash:
        return {
            "mode": "apply", "wrote": False, "success": False,
            "refused": ["PRIOR_OBLIGATION_OPEN_FOR_ANOTHER_PLAN"],
            "plan_hash": prior_hash,
            "note": (
                "An earlier apply committed rows whose calibration invalidation "
                "was never discharged. Re-apply THAT plan_hash until it does; a "
                "new plan must not run on top of an open debt."
            ),
        }

    approved = approved_leg_index(plan)
    written: list[int] = []
    drifted: list[int] = []
    attempted: list[int] = []

    for leg_id, leg in approved.items():
        if time.monotonic() - started > _MAX_SECONDS:
            break
        attempted.append(leg_id)
        # COMPARE-AND-SET on the exact prior state the dry-run READ. A rowcount
        # of zero is a named drift that reports and skips — never a silent
        # overwrite, and never a silent success.
        result = await session.execute(
            text("""
                UPDATE futures_outcomes
                SET is_winner = :wins,
                    resolution_source = :src,
                    last_updated = now()
                WHERE id = :leg_id
                  AND resolution_source IS NULL
                  AND is_winner IS NOT TRUE
            """),
            {"leg_id": leg_id, "wins": leg.verdict == "winner", "src": WRITE_SOURCE},
        )
        if result.rowcount:
            await session.commit()
            written.append(leg_id)
        else:
            await session.rollback()
            drifted.append(leg_id)

    outside = mutations_outside_approved(plan, attempted)
    contract = evaluate_repair_contract(
        candidate_ids=list(approved),
        processed_ids=attempted,
        approved_ids=plan.leg_ids,
        mutated_ids=written,
        dry_run_ids=None,
        next_cursor=None,
    )

    # THE DEBT IS PERSISTED BEFORE THE INVALIDATION IS ATTEMPTED. Rows are
    # already committed; if the process dies during the invalidation, the only
    # record of what must be discarded is this one.
    market_ids = sorted({approved[i].market_id for i in written})
    if prior_open:
        market_ids = sorted(set(market_ids) | set(obligation_market_ids(prior)))
        leg_union = sorted(set(written) | set(obligation_leg_ids(prior)))
    else:
        leg_union = sorted(written)

    obligation = new_obligation(
        plan_hash=plan.plan_hash, market_ids=market_ids,
        leg_ids=leg_union, owner=_OWNER,
    )
    ob_ok, ob_note = await _save_obligation(obligation)

    inv: dict[str, Any] = {"status": "not_attempted"}
    if market_ids:
        try:
            from app.tasks.repair_kalshi_fabricated_loss import (
                invalidate_calibration_generation,
            )

            inv = await invalidate_calibration_generation(session, market_ids)
        except Exception as exc:  # noqa: BLE001 — a debt, not a crash
            inv = {"status": f"raised:{type(exc).__name__}"}
    else:
        inv = {"status": "nothing_written"}

    discharged, why = invalidation_discharged(
        status=str(inv.get("status")),
        wrote_rows=bool(written),
        drift_count=len(drifted),
        prior_obligation_open=prior_open,
    )
    if discharged:
        ok2, note2 = await _save_obligation(
            discharge_obligation(obligation, proof=inv)
        )
        ob_ok, ob_note = (ob_ok and ok2), f"{ob_note}; discharge {note2}"

    return {
        "mode": "apply",
        "wrote": bool(written),
        "success": bool(discharged and ob_ok and not outside),
        "plan_hash": plan.plan_hash,
        "legs_written": len(written),
        "legs_drifted": len(drifted),
        "markets_touched": len(market_ids),
        "mutations_outside_approved": outside,
        "drift_reason": REASON_CONCURRENT_DRIFT if drifted else None,
        "contract": contract,
        "invalidation": inv,
        "invalidation_discharged": discharged,
        "invalidation_why": why,
        "obligation_persisted": ob_ok,
        "obligation_note": ob_note,
        "elapsed_s": round(time.monotonic() - started, 2),
        "note": (
            "success:false with legs_written>0 is an HONEST state — the rows "
            "are committed and the calibration invalidation is a persisted "
            "debt. RETRY THE SAME plan_hash. Do not re-plan."
            if written and not discharged else None
        ),
    }
