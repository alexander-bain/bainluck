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
# Attendance (CAL-P073, C-APPLY-PRE-1912-R2 input 1)
# ---------------------------------------------------------------------------
#
# The pages were already ROW-SAFE — content-addressed plan, compare-and-set,
# counted exclusions, a persisted invalidation debt. They did not compose into
# an attended PROGRAMME, and the difference is what one Alex MC is being asked
# to cover: **~5,661 calls may ride one authorisation only if mid-wave progress
# is readable.** That is the contract, not a nicety, so the three things below
# are part of the rail rather than an operator's spreadsheet.
#
# The specific defect, and it is not subtle once named: ``_dry_run`` called
# ``_load_cohort(..., before_id=None)`` unconditionally. The cohort self-drains
# on APPLY (a written row gains a ``resolution_source`` and leaves the HAVING),
# so the wave did advance — but only through applying. **Two consecutive
# dry-runs returned the identical 40 markets, forever.** An operator therefore
# could not read ahead, could not step over a page that keeps failing at the
# venue, and could not resume someone else's session. A rail whose only way to
# move forward is to write is not attendable; it is a ratchet with a human
# holding it.

#: Cumulative wave progress. One durable slot, overwritten every call, so a
#: DIFFERENT operator in a DIFFERENT session can read where the wave stands.
#: Progress kept only in a response body is progress one closed terminal
#: destroys.
PROGRESS_IDENTITY = "calibration:repair:pm_never_graded:wave_progress"
WAVE_PROGRESS_SCHEMA = "calibration-repair-wave-progress/v1"

#: Categories measured at ZERO never-graded markets. They are a tripwire on the
#: COHORT PREDICATE, not on the data: this rail crowns outcomes from a venue
#: answer, and the one failure that would not announce itself is the population
#: quietly widening to include markets nobody scoped. A canary that goes
#: non-zero means the thing being drained is no longer the thing that was
#: measured — which is precisely the claim an MC is authorising.
ZERO_POPULATION_CANARIES: tuple[str, ...] = ("rodeo", "olympics", "legal", "crypto")

#: Statement budget for the canary read. Much tighter than the full census,
#: because this runs on EVERY progress read and shares the 25 s call budget.
#: On expiry the canaries are ABSENT with a reason and the verdict is
#: ``unmeasured`` — never ``clean``. A tripwire that cannot be read has not
#: been read, and reporting that as "no canary tripped" is gotcha #53 committed
#: inside the instrument built to prevent it.
_CANARY_TIMEOUT_MS = 6_000

#: Canary verdicts.
CANARY_CLEAN = "clean"
CANARY_TRIPPED = "TRIPPED"
CANARY_UNMEASURED = "unmeasured"


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


_CANARY_SQL = f"""
    SELECT COALESCE(fm.llm_sport_category, 'unknown') AS category,
           count(*) AS markets
    FROM (
        SELECT fm.id, fm.llm_sport_category
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
          AND fm.external_id LIKE '0x%'
          AND fm.llm_sport_category = ANY(:cats)
        GROUP BY fm.id, fm.llm_sport_category
        {POPULATION_HAVING_SQL}
    ) fm
    GROUP BY 1
"""


def evaluate_canaries(
    counts: dict[str, int] | None, *, note: str
) -> dict[str, Any]:
    """Grade the zero-population tripwires. UNMEASURED IS NOT CLEAN.

    Returns a verdict per canary plus one overall, and the overall degrades in
    the safe direction: any tripped canary is ``TRIPPED``; otherwise any
    unmeasured canary is ``unmeasured``; only an all-measured, all-zero read is
    ``clean``. Pure so the precedence can be graded without a database.
    """
    if counts is None:
        return {
            "measured": False,
            "verdict": CANARY_UNMEASURED,
            "reason": note,
            "canaries": {
                name: {"markets": None, "verdict": CANARY_UNMEASURED}
                for name in ZERO_POPULATION_CANARIES
            },
            "note": (
                "A tripwire that could not be read has NOT been read. This is "
                "not a clean canary panel and must not be attended as one."
            ),
        }
    per: dict[str, Any] = {}
    for name in ZERO_POPULATION_CANARIES:
        n = int(counts.get(name, 0))
        per[name] = {
            "markets": n,
            "verdict": CANARY_CLEAN if n == 0 else CANARY_TRIPPED,
        }
    tripped = sorted(k for k, v in per.items() if v["verdict"] == CANARY_TRIPPED)
    return {
        "measured": True,
        "verdict": CANARY_TRIPPED if tripped else CANARY_CLEAN,
        "reason": note,
        "tripped": tripped,
        "canaries": per,
        "note": (
            "A canary above zero means the never-graded population now includes "
            "a category nobody scoped — the cohort predicate moved, so the "
            "measurement the MC authorised no longer describes what is being "
            "drained. HALT and re-census."
            if tripped else
            "All four measured at zero: the drained population is still the "
            "population that was measured."
        ),
    }


async def _read_canaries(session) -> dict[str, Any]:
    """Bounded read of the four canary categories. Never raises, never lies."""
    try:
        await session.execute(
            text(f"SET LOCAL statement_timeout = {_CANARY_TIMEOUT_MS}")
        )
        rows = (
            await session.execute(
                text(_CANARY_SQL), {"cats": list(ZERO_POPULATION_CANARIES)}
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        try:
            await session.rollback()
        except Exception:
            pass
        return evaluate_canaries(
            None, note=f"canary_read_failed: {type(exc).__name__}: {str(exc)[:120]}"
        )
    return evaluate_canaries({r.category: int(r.markets) for r in rows}, note="ok")


async def _load_progress() -> tuple[dict[str, Any] | None, str]:
    """``(record, note)``. A missing record is a wave that has not started."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            PROGRESS_IDENTITY,
            expected_version=WAVE_PROGRESS_SCHEMA,
            max_age_s=_OBLIGATION_MAX_AGE_S,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"progress read raised: {type(exc).__name__}"
    if read.status == "missing":
        return None, "missing"
    if not read.ok or read.envelope is None:
        return None, f"progress unreadable: {read.status}"
    payload = read.envelope.payload
    if not isinstance(payload, dict):
        return None, "progress malformed"
    return payload, "ok"


async def _save_progress(record: dict[str, Any]) -> tuple[bool, str]:
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PROGRESS_IDENTITY,
                schema_version=WAVE_PROGRESS_SCHEMA,
                payload=record,
                complete=True,
                source=_OWNER,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"progress persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"progress persist rejected: {result.get('status')}"


def fold_progress(
    prior: dict[str, Any] | None,
    *,
    mode: str,
    examined_markets: int = 0,
    planned_markets: int = 0,
    written_legs: int = 0,
    written_markets: int = 0,
    cursor: int | None,
) -> dict[str, Any]:
    """Fold one call into the cumulative wave record. Pure.

    ``calls`` counts every call including this one, which is what makes the
    ``~5,661`` in the MC checkable against reality rather than against a plan.
    The cursor is carried as ``resume_after_id`` and is deliberately allowed to
    be ``None`` — a call that examined nothing has no cursor to offer, and
    inventing one (say, the prior value) would let an operator believe a page
    was walked when it was not.
    """
    prior = prior if isinstance(prior, dict) else {}

    def _n(key: str) -> int:
        v = prior.get(key)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0

    return {
        "schema": WAVE_PROGRESS_SCHEMA,
        "owner": _OWNER,
        "cohort": "pm_never_graded",
        "issue": 1912,
        "calls": _n("calls") + 1,
        "dry_runs": _n("dry_runs") + (1 if mode == "dry_run" else 0),
        "applies": _n("applies") + (1 if mode == "apply" else 0),
        "examined_markets_total": _n("examined_markets_total") + max(0, examined_markets),
        "planned_markets_total": _n("planned_markets_total") + max(0, planned_markets),
        "written_legs_total": _n("written_legs_total") + max(0, written_legs),
        "written_markets_total": _n("written_markets_total") + max(0, written_markets),
        "last_mode": mode,
        "last_cursor": cursor,
        # The one field an operator resumes FROM. Kept at the prior value when
        # this call produced none, because the last real cursor is still the
        # right place to resume — unlike the counters, this is a position, not
        # a tally, and a position does not decay by going unused.
        "resume_after_id": cursor if cursor is not None else prior.get("resume_after_id"),
    }


async def progress_read(
    session,
    *,
    mode: str,
    examined_markets: int = 0,
    planned_markets: int = 0,
    written_legs: int = 0,
    written_markets: int = 0,
    cursor: int | None = None,
) -> dict[str, Any]:
    """The attendance block returned on EVERY dry-run and EVERY apply.

    Three things an attended programme needs and the page-at-a-time rail did
    not have: a durable identity progress can be re-read from, a resume cursor,
    and the canary panel — evaluated here rather than offered as a separate
    call, because a check an operator has to remember to run is a check that
    gets skipped on call 300 of 5,661.
    """
    canaries = await _read_canaries(session)
    prior, prior_note = await _load_progress()
    record = fold_progress(
        prior,
        mode=mode,
        examined_markets=examined_markets,
        planned_markets=planned_markets,
        written_legs=written_legs,
        written_markets=written_markets,
        cursor=cursor,
    )
    saved, save_note = await _save_progress(record)
    return {
        "identity": PROGRESS_IDENTITY,
        "schema": WAVE_PROGRESS_SCHEMA,
        "durable": saved,
        "durable_note": save_note,
        "prior_note": prior_note,
        "wave": record,
        "canaries": canaries,
        "attendance": (
            "READABLE — this block is re-derivable from the durable identity by "
            "any operator in any session."
            if saved else
            "NOT DURABLE — this call's progress exists only in this response. "
            f"({save_note}) Record the numbers before closing the terminal."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    plan_hash: str | None = None,
    after_id: int | None = None,
) -> dict[str, Any]:
    """Dry-run (build a plan) or apply (execute a reviewed one). Never both.

    Signature ordered to match the dispatcher in ``routes/admin_repairs.py``,
    which calls ``fn(db, apply, **extra)`` — ``apply`` is POSITIONAL there, and
    a keyword-only parameter would have made this repair permanently
    un-appliable while looking correct in isolation.

    ``after_id`` is the dry-run's keyset resume cursor. The dispatcher already
    declares the parameter and passes it only to repairs whose signature
    accepts one; until CAL-P073 this one did not, so the cursor arrived at the
    router and was silently dropped — the page was fixed at "the newest 40"
    on every call.
    """
    started = time.monotonic()
    if apply:
        return await _apply_reviewed_plan(session, plan_hash, started)
    return await _dry_run(
        session,
        min(limit or APPLY_MARKET_CAP, APPLY_MARKET_CAP),
        started,
        after_id=after_id,
    )


async def _dry_run(
    session, limit: int, started: float, after_id: int | None = None
) -> dict[str, Any]:
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

    # ``_load_cohort`` walks ``ORDER BY fm.id DESC``, so its keyset predicate is
    # ``fm.id < :before``. The dispatcher's vocabulary for a resume cursor is
    # ``after_id`` — "after" in WALK ORDER, which on a descending walk is a
    # smaller id. The two names are kept aligned here rather than renaming the
    # router's parameter, because that one is shared with repairs that walk
    # ascending and would then be wrong for them instead.
    rows = await _load_cohort(
        session, limit, after_id, cohort=_COHORT_NEVER_GRADED
    )
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

    # The keyset cursor for the NEXT page. The walk is id-descending, so the
    # smallest id this call examined is where the next one resumes. Derived
    # from what was EXAMINED, not from what was planned: a page whose markets
    # all excluded still moved through the population, and resuming from the
    # planned set would re-walk every exclusion forever.
    next_cursor = min(examined) if examined else None
    page_exhausted = len(rows) < limit

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
        "resumed_after_id": after_id,
        "next_cursor": next_cursor,
        "page_exhausted": page_exhausted,
        "progress": await progress_read(
            session,
            mode="dry_run",
            examined_markets=len(examined),
            planned_markets=len(plan.market_ids),
            cursor=next_cursor,
        ),
        "elapsed_s": round(time.monotonic() - started, 2),
        "next": (
            f"POST …/pm-never-graded?apply=true&plan_hash={plan.plan_hash}"
            if plan_ok else
            "NOT APPLIABLE — the plan was not persisted; re-run the dry-run."
        ),
        "next_page": (
            "POST …/pm-never-graded?after_id=" + str(next_cursor)
            if next_cursor is not None else
            "NO CURSOR — this call examined nothing, so it cannot say where to "
            "resume. Re-run; do not guess a cursor."
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
        # Attendance on the APPLY too, not just the dry-run. An apply is the
        # call that changes the population, so a wave record that only counted
        # dry-runs would drift further from the truth with every write — and
        # the canary panel is most load-bearing immediately after a write,
        # because that is when the cohort can have moved.
        "progress": await progress_read(
            session,
            mode="apply",
            written_legs=len(written),
            written_markets=len(market_ids),
            cursor=None,
        ),
        "elapsed_s": round(time.monotonic() - started, 2),
        "note": (
            "success:false with legs_written>0 is an HONEST state — the rows "
            "are committed and the calibration invalidation is a persisted "
            "debt. RETRY THE SAME plan_hash. Do not re-plan."
            if written and not discharged else None
        ),
    }
