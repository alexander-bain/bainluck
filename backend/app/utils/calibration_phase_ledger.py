"""Pure phase-ledger + checkpoint contract for the main calibration build (Queue 300M).

C124 committed the ORACLE for this behaviour
(``scripts/evals/calibration_main_phase_budget_contract.py`` + its 31-case
corpus). That evaluator grades a *plan/run/checkpoint/health* row; nothing in
the codebase emitted one for the MAIN build. This module is the missing half:
the pure helpers the build uses to construct that row, so what production
actually does is graded by the same contract the corpus encodes.

``app.tasks.calibration_main_build`` is the runtime half (timing, durable
persistence, statement timeouts, the overlap lock). Everything here is I/O-free
so the rules stay testable without a database or a clock.

Why this exists at all: ``precompute_calibration_main`` is ONE transaction
running eleven sequential reads under a single 1,500s statement timeout. There
is no partial credit — a run that dies at read 10 of 11 loses 100% of its work
and the next beat starts from zero, which is how the public page ends up
serving yesterday's population while the beat "runs" every hour. r343 recorded
a 1,502.175s last success against a 1,500s soft limit, then seven consecutive
soft-limit deaths.

The rules that matter, in the corpus's own vocabulary:

* ``PHASE_BUDGET_GUESSED`` — a phase budget is only ever DERIVED from recorded
  observations of that phase. Until the ledger has measured one, the plan is
  ``provisional``: phases carry no budget and only the single absolute deadline
  governs. Inventing a number here is the one thing Queue 300M forbids.
* ``STATEMENT_TIMEOUT_NOT_INSIDE_PHASE`` — the DB statement timeout is the
  INNER backstop (it releases the orphaned backend's xmin — gotcha #38/#39), so
  it must fire strictly before the phase budget it sits inside.
* ``DECLARED_BUDGETS_EXHAUST_SOFT_LIMIT`` — declared budgets plus the cleanup /
  gate / publication margin must fit inside the soft limit, or the build has
  budgeted itself out of the ability to publish what it just computed.
* ``CHECKPOINT_BEFORE_COMMIT`` / ``CHECKPOINT_ADVANCED_AFTER_WRITE_FAILURE`` —
  a phase is only recorded as done after its own read committed AND the
  checkpoint write succeeded. Either way round, a resumed run would skip work
  it never did.
* ``INCOMPLETE_RUN_PUBLISHED`` / ``INCOMPLETE_RUN_GREEN`` — partial is not
  done. An interrupted run keeps its progress, publishes nothing, and reports
  its terminal state honestly.
* ``STALE_ARTIFACT_GREEN`` / ``INVOCATION_ONLY_GREEN`` — health is about the
  ARTIFACT's generation, not about the task having been invoked. A ledger write
  failure makes progress UNKNOWN, never GREEN.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

PHASE_LEDGER_SCHEMA = "calibration-main-phase-ledger/v1"
MAIN_CHECKPOINT_SCHEMA = "calibration-main-checkpoint/v1"

MAIN_BUILD_TASK = "precompute_calibration_main"

# --- The four evidence-backed phase boundaries -------------------------------
#
# These are not a fresh invention: they are the grouping C124's corpus already
# grades, and they line up with the build's own natural seams — one heavy
# population CTE, three events-table reads, seven small diagnostic reads, then
# everything after the session closes. Splitting anywhere INSIDE the population
# CTE would need measured evidence that does not exist yet (Item 0's job).
PHASE_FUTURES = "futures"
PHASE_SPORTS = "sports"
PHASE_DIAGNOSTICS = "diagnostics"
#: Row materialization, bucket assembly, Wilson CIs and the bootstrap MCE — all
#: pure Python, all previously invisible. It sat between the last read and the
#: first publish stage, so every millisecond of it landed in
#: ``unmeasured_overhead`` and no budget could ever account for it.
PHASE_AGGREGATE = "aggregate"
PHASE_PUBLISH = "serialize_gate_publish"

#: Ordered, and every one of them is required — the payload is not a payload
#: without all five. Order matters: it is the resume order.
REQUIRED_PHASES: tuple[str, ...] = (
    PHASE_FUTURES,
    PHASE_SPORTS,
    PHASE_DIAGNOSTICS,
    PHASE_AGGREGATE,
    PHASE_PUBLISH,
)

#: Phases whose output is a read result that a later beat can carry forward.
#: ``aggregate`` and ``serialize_gate_publish`` are deliberately absent: they
#: consume every other phase's output and must always run against the run that
#: publishes.
RESUMABLE_PHASES: tuple[str, ...] = (PHASE_FUTURES, PHASE_SPORTS, PHASE_DIAGNOSTICS)

#: Exactly what a carried phase must hand back, per phase. Resume is
#: all-or-nothing per phase and this is what enforces it: a stored output whose
#: key set does not match EXACTLY is discarded, because a phase marked done
#: that then silently re-reads half its inputs is the worst of both worlds — it
#: pays the cost and reports it did not.
#:
#: The per-bookmaker read is deliberately absent from ``diagnostics``: it is a
#: single Redis GET, so carrying it would trade freshness for nothing.
PHASE_OUTPUT_KEYS: dict[str, frozenset[str]] = {
    PHASE_FUTURES: frozenset({"rows"}),
    PHASE_SPORTS: frozenset({"events_rows", "spreads_rows", "totals_rows"}),
    PHASE_DIAGNOSTICS: frozenset(
        {
            "total_markets",
            "closing_row",
            "void_excluded",
            "heuristic_excluded",
            "soccer_2way_excluded",
            "truth_by_class",
            "date_range",
        }
    ),
}

# Phase statuses. A phase is exactly one of these.
PENDING = "pending"
RUNNING = "running"
COMPLETE = "complete"
RESUMED = "resumed"  # carried from a prior beat's committed checkpoint
TIMEOUT = "timeout"
CANCELLED = "cancelled"
FAILED = "failed"

#: Statuses that mean "this phase's output exists and is trustworthy".
DONE_STATUSES = frozenset({COMPLETE, RESUMED})

#: Statuses whose elapsed time is a measured LOWER BOUND on the phase's cost:
#: the phase ran for that long and still had not finished. Not a duration, so
#: never a budget — but the only thing a never-completing phase can teach.
FLOOR_STATUSES = frozenset({TIMEOUT, CANCELLED, FAILED})

# --- Feasibility verdicts (CAL-P067, ruling 075's instrument) -----------------
#
# Four values, because the instrument previously had two and needed four. It
# could say "a phase cannot fit" and it could say nothing; it had no way at all
# to say "I could not tell", so every could-not-tell was emitted as a
# nothing-to-report and read as an all-clear for sixteen consecutive beats.
#
# The distinction that matters is EVIDENCE CLASS, not magnitude:
#
# * A COMPLETED phase (or a completed unit of one) yields a duration. A duration
#   settles feasibility in both directions.
# * A CANCELLED phase yields elapsed-at-cancellation. That is a lower bound on
#   an unknown cost, and it settles feasibility in ONE direction only — at or
#   past the ceiling it proves the phase cannot fit; anywhere below the ceiling
#   it proves nothing whatsoever, because the true cost may lie on either side.
#
# Comparing the second class as though it were the first is the whole defect.
#: Measured to fit: a completed duration (whole phase, or one unit of it) that
#: lands under the ceiling.
FEASIBILITY_FEASIBLE = "feasible"
#: Measured NOT to fit, conclusively — a completed unit larger than a whole
#: beat, or a floor at/past the ceiling. No budget, checkpoint or resume helps.
FEASIBILITY_INFEASIBLE = "infeasible"
#: Evidence exists but does not settle it: a floor strictly below the ceiling
#: and no completion. The phase ran that long and did not finish; its true cost
#: is unknown and strictly greater. **Not** an all-clear.
FEASIBILITY_INDETERMINATE = "indeterminate"
#: No evidence at all — nothing has ever been measured for this phase.
FEASIBILITY_NO_DATA = "no_data"

#: Worst-first. The plan takes the worst verdict across its required phases,
#: because the build publishes all-or-nothing: the weakest phase IS the plan.
#: Both could-not-conclude states deliberately outrank ``feasible``, so a plan is
#: never called feasible on the strength of the phases that happened to be
#: measurable.
FEASIBILITY_PRECEDENCE: tuple[str, ...] = (
    FEASIBILITY_INFEASIBLE,
    FEASIBILITY_INDETERMINATE,
    FEASIBILITY_NO_DATA,
    FEASIBILITY_FEASIBLE,
)

# Run terminal states, matching the corpus's ``run.terminal`` vocabulary.
TERMINAL_COMPLETE = "complete"
TERMINAL_PARTIAL = "partial"
TERMINAL_FAILED = "failed"
TERMINAL_CANCELLED = "cancelled"
TERMINAL_HARD_LOSS = "hard_loss"
TERMINAL_OVERLAP_REFUSED = "overlap_refused"

# Checkpoint load actions.
FRESH = "fresh"
RESUME = "resume"
INVALIDATE = "invalidate"
REFUSE = "refuse"

# Health verdicts (lowercase, matching the corpus's ``health.verdict``).
GREEN = "green"
UNKNOWN = "unknown"
RED = "red"
PARTIAL = "partial"

# --- Deadline geometry -------------------------------------------------------
#
# These three are NOT budget guesses; they are the deployed Celery limits read
# back off the task decorator, plus the margin the build needs AFTER its last
# read to serialize, gate, publish durably, accelerate into Redis, close the
# session and let the wrapper record a terminal. Everything per-phase is
# derived from measurement.
SOFT_LIMIT_MS = 1_500_000  # celery soft_time_limit=1500
HARD_LIMIT_MS = 1_560_000  # celery time_limit=1560

#: Reserved out of the soft limit for serialize + gate + durable publish +
#: Redis + session cleanup + wrapper exit. Sized from the stage timings the
#: build already reports (``serialize_ms`` / ``publish_ms``) plus the durable
#: write's own 5s statement timeout and a session-close allowance.
CLEANUP_MARGIN_MS = 120_000

#: The one absolute deadline every phase is planned against.
PHASE_DEADLINE_MS = SOFT_LIMIT_MS - CLEANUP_MARGIN_MS

#: How far inside its phase budget the DB statement timeout fires. The gap is
#: what lets Postgres cancel the statement (releasing xmin) and the Python side
#: still record the timeout in the ledger before the phase budget expires.
STATEMENT_INNER_MARGIN_MS = 30_000

#: A budget is ``max(observed) * this``. Applied to a MEASURED input, so the
#: result stays a measurement with headroom rather than an invented number.
BUDGET_SAFETY = 1.5

#: One recorded observation of a phase is a measurement. Zero is a guess.
MIN_OBSERVATIONS = 1

#: Rolling window of per-phase durations kept in the durable ledger. Bounded so
#: the ledger row cannot grow without limit, long enough that one anomalous
#: beat cannot permanently inflate a budget once it ages out.
HISTORY_WINDOW = 10


# =============================================================================
# Plan
# =============================================================================


@dataclass(frozen=True)
class PhaseBudget:
    """What one phase is allowed to cost, and where that number came from."""

    name: str
    required: bool
    budget_ms: Optional[int]
    statement_timeout_ms: Optional[int]
    measured_input: bool
    observations: int = 0
    #: Worst observed "ran this long and did NOT finish" duration. A lower
    #: bound, deliberately kept apart from ``budget_ms``: a floor can say a
    #: phase does not fit, but it can never say how long the phase takes.
    floor_ms: Optional[int] = None
    floor_observations: int = 0
    #: Mean cost of ONE completed unit of a unit-staged phase, and the partition
    #: it belongs to. This is a completed duration — the strongest evidence the
    #: build produces about the futures phase — and until CAL-P067 no
    #: feasibility check read it, which is why "is it converging?" had to be
    #: answered by polling the durable cursor from outside the application.
    unit_ms: Optional[int] = None
    units_total: Optional[int] = None
    units_done: Optional[int] = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "budget_ms": self.budget_ms,
            "statement_timeout_ms": self.statement_timeout_ms,
            "measured_input": self.measured_input,
            "observations": self.observations,
            "floor_ms": self.floor_ms,
            "floor_observations": self.floor_observations,
            "unit_ms": self.unit_ms,
            "units_total": self.units_total,
            "units_done": self.units_done,
        }


@dataclass(frozen=True)
class PhasePlan:
    """The budget assignment for one run, and whether it rests on measurement."""

    budgets: tuple[PhaseBudget, ...]
    soft_limit_ms: int = SOFT_LIMIT_MS
    hard_limit_ms: int = HARD_LIMIT_MS
    cleanup_margin_ms: int = CLEANUP_MARGIN_MS

    @property
    def provisional(self) -> bool:
        """True while ANY phase budget is not yet backed by an observation.

        A provisional plan is not a broken plan — it is the honest state of a
        build nobody has measured yet. It runs under the single absolute
        deadline and records what every phase actually cost, which is what
        turns the NEXT run's plan into a measured one.
        """
        return any(not b.measured_input for b in self.budgets)

    @property
    def available_ms(self) -> int:
        """The one absolute window every phase is planned against."""
        return max(1, self.soft_limit_ms - self.cleanup_margin_ms)

    @property
    def max_phase_ms(self) -> int:
        """The longest a phase can ever run: the statement timeout it gets when
        it is handed the entire window.

        NOT ``available_ms``. The inner backstop deliberately fires
        :data:`STATEMENT_INNER_MARGIN_MS` early so Postgres cancels the
        statement and releases its xmin before Celery SIGKILLs the worker, so a
        floor can never actually reach the raw window — comparing against it
        would make infeasibility unreachable by construction.
        """
        return _statement_timeout_for(self.available_ms)

    def phase_feasibility(self, name: str) -> str:
        """Can this phase fit a beat? — answered ONLY from measured cost.

        The evidence ladder, strongest first. Each rung is a different KIND of
        measurement, and the ordering is the whole correctness argument:

        1. **A completed unit** (``unit_ms``, backed by ``units_done >= 1``).
           The unit finished, so this is a duration. If one unit is larger than
           a whole beat the phase is conclusively infeasible — a staged cursor
           can carry work between beats but it cannot split a unit, so no amount
           of resuming ever finishes it. Otherwise the phase converges.
        2. **A completed phase** (``measured_input``). Also a duration; it fit
           at least once, and ``derive_plan`` has already turned it into a
           budget.
        3. **A floor at or past the ceiling.** Elapsed-at-cancellation is only a
           lower bound, but a lower bound past the ceiling still settles it: the
           phase ran a whole reachable window and did not finish.
        4. **A floor below the ceiling** — ``indeterminate``. The one rung that
           used to be silently treated as rung 2's negation. ``1,181,045 <
           1,350,000`` says the phase ran 1,181,045 ms without finishing; the
           true cost is unknown and strictly greater, and may be on either side
           of the ceiling. Concluding "fits" here is not a weak inference, it is
           no inference at all.
        5. **Nothing** — ``no_data``.
        """
        budget = self.by_name(name)
        if budget is None:
            return FEASIBILITY_NO_DATA
        ceiling = self.max_phase_ms

        if budget.unit_ms is not None and budget.units_done:
            return (
                FEASIBILITY_INFEASIBLE if budget.unit_ms >= ceiling else FEASIBILITY_FEASIBLE
            )
        if budget.measured_input and budget.observations:
            return FEASIBILITY_FEASIBLE
        if budget.floor_ms is not None:
            return (
                FEASIBILITY_INFEASIBLE
                if budget.floor_ms >= ceiling
                else FEASIBILITY_INDETERMINATE
            )
        return FEASIBILITY_NO_DATA

    def _phases_with(self, verdict: str) -> tuple[str, ...]:
        return tuple(
            b.name
            for b in self.budgets
            if b.required and self.phase_feasibility(b.name) == verdict
        )

    @property
    def infeasible_phases(self) -> tuple[str, ...]:
        """Required phases MEASURED to not fit the window.

        Unchanged in meaning and deliberately so — this is the CONCLUSIVE
        bucket. What changed is that its emptiness is no longer the only thing
        a reader sees: an empty list here now sits beside a verdict that says
        whether the check concluded, so "nothing is broken" and "nothing was
        checked" stop sharing a rendering.
        """
        return self._phases_with(FEASIBILITY_INFEASIBLE)

    @property
    def indeterminate_phases(self) -> tuple[str, ...]:
        """Required phases whose only evidence is a floor short of the ceiling."""
        return self._phases_with(FEASIBILITY_INDETERMINATE)

    @property
    def unchecked_phases(self) -> tuple[str, ...]:
        """Required phases with no measurement of any kind."""
        return self._phases_with(FEASIBILITY_NO_DATA)

    @property
    def feasible_phases(self) -> tuple[str, ...]:
        """Required phases a completed duration proves will fit."""
        return self._phases_with(FEASIBILITY_FEASIBLE)

    @property
    def feasibility(self) -> str:
        """The worst verdict across required phases (see FEASIBILITY_PRECEDENCE)."""
        verdicts = {self.phase_feasibility(b.name) for b in self.budgets if b.required}
        for verdict in FEASIBILITY_PRECEDENCE:
            if verdict in verdicts:
                return verdict
        return FEASIBILITY_NO_DATA

    def unit_projection(self, name: str) -> Optional[dict[str, int]]:
        """How many units are left and how many beats that is, from MEASURED cost.

        ``beats_remaining = -1`` keeps the convention ``_record_staged_rate``
        already uses: it is not "unknown", it is "a whole beat cannot hold one
        unit", which is a different and much worse fact than a large count.

        **The divisor is the phase's OWN allotment, not the whole-beat ceiling
        (CAL-P071).** This used to divide by :attr:`max_phase_ms`, which is the
        statement timeout a phase gets *when it is handed the entire window* —
        the right ceiling for the feasibility question ("could this phase ever
        fit?") and the wrong one for the throughput question ("how many units
        will a beat actually finish?"). The two questions are not the same
        question, and the plan itself says so: on 2026-08-18 the first q268 build
        allotted ``futures`` a ``budget_ms`` of 177,374 against a
        ``max_phase_ms`` of 1,350,000, so the projection assumed the phase got
        **7.6x the beat it was given** and reported ``units_per_beat: 10``,
        ``beats_remaining: 13``. The truth was 1 and 125 — five days, against a
        hard artifact-expiry deadline 52 hours out.

        It failed in the dangerous direction twice over. Optimistic, and
        **immovable**: three consecutive beats banked 2, 1 and 0 units while the
        estimate sat at 13 throughout, because observed throughput is not an
        input to it. An ETA that cannot fall as the build slows is not an
        estimate, it is a constant wearing one.

        ``per_beat_basis`` names which divisor produced the number, so a phase
        with no declared budget (which legitimately falls back to the ceiling)
        can never be mistaken for one that has been measured against its own.
        """
        budget = self.by_name(name)
        if budget is None or budget.unit_ms is None or not budget.units_done:
            return None
        total = budget.units_total or 0
        remaining = max(0, total - (budget.units_done or 0))
        if budget.budget_ms:
            per_beat_ms = budget.budget_ms
            basis = "phase_budget"
        else:
            per_beat_ms = self.max_phase_ms
            basis = "whole_beat_ceiling"
        per_beat = per_beat_ms // budget.unit_ms
        return {
            "unit_ms": budget.unit_ms,
            "units_total": total,
            "units_done": budget.units_done or 0,
            "units_remaining": remaining,
            "units_per_beat": per_beat,
            "per_beat_ms": per_beat_ms,
            "per_beat_basis": basis,
            "beats_remaining": (
                math.ceil(remaining / per_beat) if per_beat >= 1 else -1
            ),
        }

    def by_name(self, name: str) -> Optional[PhaseBudget]:
        for budget in self.budgets:
            if budget.name == name:
                return budget
        return None

    @property
    def declared_ms(self) -> int:
        return sum(b.budget_ms or 0 for b in self.budgets)

    def as_payload(self) -> dict[str, Any]:
        verdict = self.feasibility
        infeasible = self.infeasible_phases
        units = {
            b.name: projection
            for b in self.budgets
            if (projection := self.unit_projection(b.name)) is not None
        }
        return {
            # The feasibility verdict outranks the budget-derivation state, and
            # BOTH could-not-conclude verdicts outrank a bland ``provisional``.
            # Before CAL-P067 this field read ``provisional`` whether the plan
            # had been checked and passed or never checked at all, and the
            # sibling ``infeasible_phases: []`` said the same thing both ways.
            "status": (
                verdict
                if verdict != FEASIBILITY_FEASIBLE
                else ("provisional" if self.provisional else "measured")
            ),
            "soft_limit_ms": self.soft_limit_ms,
            "hard_limit_ms": self.hard_limit_ms,
            "cleanup_margin_ms": self.cleanup_margin_ms,
            "deadline_ms": self.soft_limit_ms - self.cleanup_margin_ms,
            "declared_ms": self.declared_ms,
            "infeasible_phases": list(infeasible),
            # The bucket that makes an empty ``infeasible_phases`` readable.
            # Every required phase lands in exactly one of the four lists, so a
            # reader can always tell which of the two empties they are holding.
            "feasibility": {
                "verdict": verdict,
                "checked_against_ms": self.max_phase_ms,
                "infeasible_phases": list(infeasible),
                "indeterminate_phases": list(self.indeterminate_phases),
                "unchecked_phases": list(self.unchecked_phases),
                "feasible_phases": list(self.feasible_phases),
                "units": units,
            },
            "phases": [b.as_payload() for b in self.budgets],
        }


def _statement_timeout_for(budget_ms: int) -> int:
    """The inner backstop: strictly less than the phase budget, always >= 1ms."""
    gap = max(1, min(STATEMENT_INNER_MARGIN_MS, budget_ms // 10))
    return max(1, budget_ms - gap)


def _decode_unit_cost(raw: Any) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Validate one phase's measured unit cost, or return all-``None``.

    Everything here degrades to ``None`` rather than to a number, because the
    only thing worse than an absent feasibility check is a confident one built
    on junk. ``units_done`` must be at least 1: ``unit_ms`` is a mean over
    COMPLETED units, so with none completed there is no completed duration
    behind it, whatever the field says.
    """

    def _pos_int(value: Any) -> Optional[int]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return int(value) if value > 0 else None

    if not isinstance(raw, dict):
        return None, None, None
    unit_ms = _pos_int(raw.get("unit_ms"))
    units_total = _pos_int(raw.get("units_total"))
    units_done = _pos_int(raw.get("units_done"))
    if unit_ms is None or units_total is None or units_done is None:
        return None, None, None
    return unit_ms, units_total, units_done


def derive_plan(
    history: Optional[dict[str, Any]] = None,
    *,
    floors: Optional[dict[str, Any]] = None,
    unit_costs: Optional[dict[str, Any]] = None,
    phases: Iterable[str] = REQUIRED_PHASES,
    soft_limit_ms: int = SOFT_LIMIT_MS,
    hard_limit_ms: int = HARD_LIMIT_MS,
    cleanup_margin_ms: int = CLEANUP_MARGIN_MS,
) -> PhasePlan:
    """Build this run's plan from the ledger's recorded per-phase durations.

    ``history`` maps a phase name to a list of observed ``duration_ms``. A phase
    with at least :data:`MIN_OBSERVATIONS` gets ``max(observed) * BUDGET_SAFETY``
    and is flagged ``measured_input``; a phase with none gets ``None`` and the
    plan reports itself ``provisional``. There is deliberately no third branch
    where a plausible-looking constant is filled in — that is the exact failure
    Queue 300M's Item 0 acceptance names.

    When every phase IS measured and the declared budgets plus the cleanup
    margin would overrun the soft limit, budgets are scaled DOWN proportionally
    so publication headroom survives. Scaling a measured budget down is honest
    (the build genuinely does not have that much time); scaling it up would not
    be.

    ``floors`` carries the same shape for phases that ran out of time instead of
    finishing. It NEVER produces a budget — a phase cancelled at 1,355s took
    longer than 1,355s by an unknown amount, so treating that as its duration
    would under-budget it by construction. It only lets the plan report a
    required phase as infeasible once its floor has swallowed the whole window.

    **And it concludes in that direction ONLY (CAL-P067).** A floor *below* the
    ceiling licenses nothing at all: the phase ran that long without finishing,
    so its cost is unknown and strictly greater, and may sit on either side of
    the ceiling. Such a phase reads ``indeterminate``, never feasible. This is
    the defect ruling 075's own instrument shipped with — production's
    ``floors[futures] = 1,181,045`` was ranked against a 1,350,000 ms ceiling,
    passed, and rendered ``infeasible_phases: []``.

    ``unit_costs`` maps a phase to ``{"unit_ms", "units_total", "units_done"}``
    for unit-staged phases. Unlike a floor this IS a completed duration — the
    mean of units that finished — so it settles feasibility in both directions,
    and it is the only input that can. It is what ``_record_staged_rate``
    already measures every beat and nothing previously read.
    """
    history = history or {}
    floors = floors or {}
    unit_costs = unit_costs or {}
    raw: list[tuple[str, Optional[int], bool, int, Optional[int], int]] = []
    for name in phases:
        observations = [
            int(v)
            for v in (history.get(name) or [])
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
        ]
        floor_seen = [
            int(v)
            for v in (floors.get(name) or [])
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
        ]
        floor_ms = max(floor_seen) if floor_seen else None
        if len(observations) >= MIN_OBSERVATIONS:
            raw.append(
                (
                    name,
                    max(1, math.ceil(max(observations) * BUDGET_SAFETY)),
                    True,
                    len(observations),
                    floor_ms,
                    len(floor_seen),
                )
            )
        else:
            raw.append((name, None, False, len(observations), floor_ms, len(floor_seen)))

    measured = all(flag for _, _, flag, _, _, _ in raw)
    available = max(1, soft_limit_ms - cleanup_margin_ms)
    total = sum(ms or 0 for _, ms, _, _, _, _ in raw)
    scale = 1.0
    if measured and total > available:
        scale = available / total

    budgets = []
    for name, ms, flag, count, floor_ms, floor_count in raw:
        budget_ms = max(1, int(ms * scale)) if ms is not None else None
        unit_ms, units_total, units_done = _decode_unit_cost(unit_costs.get(name))
        budgets.append(
            PhaseBudget(
                name=name,
                required=True,
                budget_ms=budget_ms,
                statement_timeout_ms=(
                    _statement_timeout_for(budget_ms) if budget_ms is not None else None
                ),
                measured_input=flag,
                observations=count,
                floor_ms=floor_ms,
                floor_observations=floor_count,
                unit_ms=unit_ms,
                units_total=units_total,
                units_done=units_done,
            )
        )
    return PhasePlan(
        budgets=tuple(budgets),
        soft_limit_ms=soft_limit_ms,
        hard_limit_ms=hard_limit_ms,
        cleanup_margin_ms=cleanup_margin_ms,
    )


def merge_history(
    history: Optional[dict[str, Any]], observations: dict[str, int]
) -> dict[str, list[int]]:
    """Fold this run's measured phase durations into the rolling window."""
    merged: dict[str, list[int]] = {}
    for name, values in (history or {}).items():
        if not isinstance(values, list):
            continue
        merged[name] = [
            int(v)
            for v in values
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
        ][-HISTORY_WINDOW:]
    for name, duration in observations.items():
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            continue
        if duration < 0:
            continue
        merged[name] = (merged.get(name, []) + [int(duration)])[-HISTORY_WINDOW:]
    return merged


# =============================================================================
# Ledger
# =============================================================================


@dataclass
class PhaseRecord:
    """One phase's measured life, in the vocabulary C124's evaluator grades."""

    name: str
    required: bool = True
    measured_input: bool = False
    budget_ms: Optional[int] = None
    statement_timeout_ms: Optional[int] = None
    duration_ms: int = 0
    status: str = PENDING
    committed: bool = False
    checkpoint_write: str = "not_attempted"
    checkpoint_advanced: bool = False
    detail: Optional[str] = None
    output_bytes: Optional[int] = None
    output_stored: Optional[bool] = None

    def as_payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "required": self.required,
            "measured_input": self.measured_input,
            "budget_ms": self.budget_ms,
            "statement_timeout_ms": self.statement_timeout_ms,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "committed": self.committed,
            "checkpoint_write": self.checkpoint_write,
            "checkpoint_advanced": self.checkpoint_advanced,
        }
        if self.detail:
            payload["detail"] = self.detail[:200]
        if self.output_bytes is not None:
            payload["output_bytes"] = self.output_bytes
        if self.output_stored is not None:
            payload["output_stored"] = self.output_stored
        return payload


class PhaseLedger:
    """Mutable, I/O-free recorder for one main-build run.

    The whole point is that the ledger is written even when — *especially* when
    — the run dies. A phase left ``running`` when the process is cancelled is
    closed out as ``cancelled`` with its elapsed time intact, so the next plan
    still learns something from a run that published nothing.
    """

    def __init__(
        self,
        *,
        plan: PhasePlan,
        population_version: str,
        owner: str,
        generation: int,
        input_fingerprint: str,
        phases: Iterable[str] = REQUIRED_PHASES,
    ) -> None:
        self.plan = plan
        self.population_version = population_version
        self.owner = owner
        self.generation = generation
        self.input_fingerprint = input_fingerprint
        self.records: dict[str, PhaseRecord] = {}
        self.order: list[str] = []
        for name in phases:
            budget = plan.by_name(name)
            self.records[name] = PhaseRecord(
                name=name,
                required=True,
                measured_input=bool(budget.measured_input) if budget else False,
                budget_ms=budget.budget_ms if budget else None,
                statement_timeout_ms=budget.statement_timeout_ms if budget else None,
            )
            self.order.append(name)
        self._open: Optional[str] = None
        self._open_at_ms: int = 0
        self.unmeasured_overhead_ms: int = 0
        self.elapsed_ms: int = 0
        self.ledger_write: str = "not_attempted"
        #: Sub-phase timings. Phases are the BUDGET and RESUME unit; stages are
        #: pure measurement inside one, and they are what turns "967s went
        #: somewhere" into "967s went here". Recorded for every stage Queue
        #: 300M Item 0 names — session acquisition, each read, serialization,
        #: baseline/gate/filing, durable publish, Redis acceleration, session
        #: cleanup — without adding a phase the C124 contract would have to
        #: budget separately.
        self.stages: dict[str, int] = {}
        #: How many observations went into each :attr:`stages` total.
        #:
        #: CAL-P066 (#1680). ``record_stage`` accumulates, so
        #: ``read:futures_unit = 1,077,573`` is a SUM over an unknown number of
        #: units. The divisor — how many units this beat actually ran, and so
        #: what one costs — was recorded only by
        #: ``_record_convergence_projection``, which runs AFTER the unit loop and
        #: is therefore skipped on every beat that ends in
        #: ``StagedFuturesIncomplete``, i.e. all of them. Production ledgers
        #: carry the sum and not the count, and the producer's convergence had
        #: to be reconstructed by polling the durable cursor from outside the
        #: application every 60 seconds.
        #:
        #: Kept beside the sum rather than replacing it: the sum is what the
        #: budget reasons about, the count is what says whether the build will
        #: finish. A counter that cannot say how many things it counted can only
        #: answer "where did the time go", never "how much is left".
        self.stage_counts: dict[str, int] = {}
        #: The COMPLETED-only half of the two tallies above, and the only one a
        #: cost may be derived from.
        #:
        #: CAL-P067. ``PhaseRunner.stage`` times its body "whatever happens
        #: inside it" — deliberately, because the stage that blew up is the one
        #: worth costing. The consequence is that ``stages[name]`` is a sum over
        #: MIXED EVIDENCE KINDS: completed stretches, which are durations, plus
        #: however far a cancelled one got, which is a lower bound on an unknown
        #: duration. Their mean is not a cost of anything.
        #:
        #: It also biases in the dangerous direction. A beat runs N units and
        #: the last is usually cancelled at the deadline, so the truncated
        #: observation drags the mean DOWN and the phase looks cheaper than it
        #: is — the instrument would under-state its way to ``feasible``, which
        #: is the same mistake as ranking a floor against the ceiling, one level
        #: down and harder to see.
        self.stage_ok_totals: dict[str, int] = {}
        self.stage_ok_counts: dict[str, int] = {}

    def record_stage(self, name: str, duration_ms: int) -> None:
        """Add a COMPLETED stage observation. Repeats accumulate (7 diagnostic reads).

        Two-argument callers are unchanged and mean what they always meant: the
        stretch ran to completion, so its elapsed time is a duration.
        """
        self.record_stage_outcome(name, duration_ms, completed=True)

    def record_stage_outcome(self, name: str, duration_ms: int, *, completed: bool) -> None:
        """Add a stage observation, recording whether the body finished.

        Both tallies always move; only a completed stretch also lands in the
        completed-only one. Keeping both is the point — the all-observations sum
        still answers "where did the 967 seconds go", which is what stages were
        built for, while the completed-only mean answers "what does one of these
        cost", which is the only question feasibility may ask.
        """
        ms = max(0, int(duration_ms))
        self.stages[name] = self.stages.get(name, 0) + ms
        self.stage_counts[name] = self.stage_counts.get(name, 0) + 1
        if completed:
            self.stage_ok_totals[name] = self.stage_ok_totals.get(name, 0) + ms
            self.stage_ok_counts[name] = self.stage_ok_counts.get(name, 0) + 1

    def stage_mean_ms(self, name: str) -> float | None:
        """Mean cost of one ``name`` observation, or ``None`` if none were made.

        ``None`` is "this beat ran no such stage", which is a different fact
        from a mean of zero and must not render as one (ruling 075, second
        clause). A caller that wants to publish the mean must decide what to say
        when there is no sample; it may not be handed a fabricated one.

        Note this is the MIXED mean (see :attr:`stage_ok_totals`). It is the
        right number for attributing elapsed time and the wrong one for costing
        a unit; use :meth:`stage_completed_mean_ms` for the latter.
        """
        count = self.stage_counts.get(name, 0)
        if count <= 0:
            return None
        return self.stages.get(name, 0) / count

    def stage_completed_count(self, name: str) -> int:
        """How many ``name`` stretches ran to completion."""
        return self.stage_ok_counts.get(name, 0)

    def stage_completed_mean_ms(self, name: str) -> float | None:
        """Mean cost of one COMPLETED ``name`` stretch, or ``None``.

        ``None`` when nothing of that name has ever finished — which is a real
        and important state (every unit cancelled) and must not be papered over
        with the mean of the truncated attempts.
        """
        count = self.stage_ok_counts.get(name, 0)
        if count <= 0:
            return None
        return self.stage_ok_totals.get(name, 0) / count

    def record_gauge(self, name: str, value: int) -> None:
        """Set a LEVEL, replacing any prior reading — CAL-P024c.

        :meth:`record_stage` is a counter: repeats accumulate, which is right
        for durations (the futures unit read is timed 128 times and the total is
        the number you want) and silently wrong for anything that is a level
        rather than an amount. An RSS reading of 400 MB recorded through
        ``record_stage`` on 128 units publishes 51,200 — a number that looks
        like a catastrophe, is not one, and is not even in megabytes any more.

        Same store, so everything that already reads ``stages`` keeps working;
        different write rule, so a gauge cannot be summed into fiction. Names
        are prefixed (``rss:``) to keep the two kinds legible side by side.
        """
        self.stages[name] = int(value)

    # -- lifecycle ------------------------------------------------------------

    def begin(self, name: str, *, now_ms: int) -> None:
        record = self.records[name]
        record.status = RUNNING
        self._open = name
        self._open_at_ms = now_ms

    def complete(self, name: str, *, now_ms: int, committed: bool = True) -> int:
        record = self.records[name]
        record.duration_ms = max(0, now_ms - self._open_at_ms) if self._open == name else record.duration_ms
        record.status = COMPLETE
        record.committed = committed
        self._open = None
        return record.duration_ms

    def carry(self, name: str, *, source_generation: Optional[int] = None) -> None:
        """Mark a phase as satisfied by a prior beat's committed checkpoint.

        Its duration stays 0 for THIS run — it cost nothing here — and it is
        never fed back into the budget history, because a carried phase is not
        an observation of how long that read takes.
        """
        record = self.records[name]
        record.status = RESUMED
        record.committed = True
        record.duration_ms = 0
        record.detail = (
            f"carried from checkpoint generation {source_generation}"
            if source_generation is not None
            else "carried from checkpoint"
        )

    def fail(self, name: str, *, now_ms: int, status: str, detail: str = "") -> None:
        record = self.records[name]
        if self._open == name:
            record.duration_ms = max(0, now_ms - self._open_at_ms)
        record.status = status
        record.committed = False
        # A phase that did not commit cannot have a legitimately advanced
        # checkpoint behind it, so the flag is cleared rather than left to
        # contradict ``committed`` in the emitted contract row.
        record.checkpoint_advanced = False
        record.detail = detail or None
        self._open = None

    def close_open_phase(self, *, now_ms: int, status: str, detail: str = "") -> None:
        """Close whatever phase was in flight when the run died."""
        if self._open is not None:
            self.fail(self._open, now_ms=now_ms, status=status, detail=detail)

    def note_checkpoint(self, name: str, *, write: str, advanced: bool) -> None:
        """Record the checkpoint write for a phase.

        ``advanced`` is forced False unless the phase's own work committed AND
        the write succeeded — the two refusals C124 grades
        (``CHECKPOINT_BEFORE_COMMIT``, ``CHECKPOINT_ADVANCED_AFTER_WRITE_FAILURE``)
        are enforced here rather than trusted to every call site.
        """
        record = self.records[name]
        record.checkpoint_write = write
        record.checkpoint_advanced = bool(advanced and record.committed and write == "ok")

    def note_output(self, name: str, *, size_bytes: int, stored: bool) -> None:
        record = self.records[name]
        record.output_bytes = int(size_bytes)
        record.output_stored = bool(stored)

    # -- derived --------------------------------------------------------------

    @property
    def completed_required(self) -> tuple[str, ...]:
        return tuple(n for n in self.order if self.records[n].status in DONE_STATUSES)

    @property
    def all_required_done(self) -> bool:
        return all(self.records[n].status in DONE_STATUSES for n in self.order)

    def observations(self) -> dict[str, int]:
        """Durations worth feeding back into the next plan.

        Only phases that ran to completion IN THIS RUN. A timeout tells you the
        phase is slower than the bound, not how long it takes; a carried phase
        tells you nothing at all.
        """
        return {
            n: r.duration_ms
            for n, r in self.records.items()
            if r.status == COMPLETE and r.duration_ms >= 0
        }

    def floors(self) -> dict[str, int]:
        """Lower bounds worth feeding back: phases that ran and did not finish.

        The counterpart to :meth:`observations`. Sixteen consecutive beats that
        all died in the same phase used to teach the next plan exactly nothing,
        because a timeout is not a duration and was therefore dropped. It is
        still not a duration — but "ran 1,355s and was cancelled" is a real
        measurement of the one thing that matters here, which is whether the
        phase can fit at all.
        """
        return {
            n: r.duration_ms
            for n, r in self.records.items()
            if r.status in FLOOR_STATUSES and r.duration_ms >= 0
        }

    def remaining_ms(self, *, elapsed_ms: int) -> int:
        return max(0, (self.plan.soft_limit_ms - self.plan.cleanup_margin_ms) - elapsed_ms)

    def statement_timeout_for(self, name: str, *, elapsed_ms: int) -> int:
        """The DB-level backstop for this phase, right now.

        Always the tighter of (a) the phase's own measured budget minus its
        inner margin and (b) whatever is left before the absolute deadline. On
        a provisional plan only (b) exists — which is still a real bound, and
        crucially still an INNER one: it fires before the Celery soft limit, so
        Postgres cancels the statement and releases its xmin instead of the
        worker being SIGKILLed into an orphaned backend (gotcha #38/#39, the
        28h41m orphan that drove the bloat spiral).
        """
        deadline_bound = _statement_timeout_for(max(2, self.remaining_ms(elapsed_ms=elapsed_ms)))
        budget = self.records[name].statement_timeout_ms
        return max(1, min(deadline_bound, budget) if budget else deadline_bound)

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": PHASE_LEDGER_SCHEMA,
            "task": MAIN_BUILD_TASK,
            "population_version": self.population_version,
            "owner": self.owner,
            "generation": self.generation,
            "input_fingerprint": self.input_fingerprint,
            "plan": self.plan.as_payload(),
            "phases": [self.records[n].as_payload() for n in self.order],
            "stages": dict(sorted(self.stages.items())),
            # The divisor for every accumulating entry in ``stages`` above.
            # Without it a sum of 1,077,573 ms is unreadable: it is one slow
            # unit or ten ordinary ones, and those say opposite things about
            # whether the build converges (CAL-P066, #1680).
            "stage_counts": dict(sorted(self.stage_counts.items())),
            "elapsed_ms": self.elapsed_ms,
            "unmeasured_overhead_ms": self.unmeasured_overhead_ms,
            "completed_required": list(self.completed_required),
        }


def phase_ledger_row(
    ledger: PhaseLedger,
    *,
    terminal: str,
    published: bool,
    durable: str,
    volatile: str,
    artifact_generation: Optional[int],
    gate: str,
    checkpoint_action: str,
    checkpoint_owner: str,
    checkpoint_version: str,
    checkpoint_advanced: bool,
    previous_preserved: bool,
    health_verdict: str,
    artifact_fresh: bool,
    health_generation: Optional[int],
    cancellation: Optional[dict[str, Any]] = None,
    oldest_tail_required: bool = False,
    oldest_tail_reached: bool = True,
) -> dict[str, Any]:
    """Emit exactly the row shape C124's evaluator grades.

    Production and the corpus speak one vocabulary: the build fills this in
    from what it actually did, and the test feeds it to ``evaluate_case`` and
    asserts no errors. A future change that breaks the contract fails a test
    instead of a night of calibration.
    """
    return {
        "plan": {
            "soft_limit_ms": ledger.plan.soft_limit_ms,
            "hard_limit_ms": ledger.plan.hard_limit_ms,
            "cleanup_margin_ms": ledger.plan.cleanup_margin_ms,
            "phases": [ledger.records[n].as_payload() for n in ledger.order],
        },
        "run": {
            "terminal": terminal,
            "elapsed_ms": ledger.elapsed_ms,
            "unmeasured_overhead_ms": ledger.unmeasured_overhead_ms,
            "published": published,
            "durable": durable,
            "volatile": volatile,
            "artifact_generation": artifact_generation,
            "population_version": ledger.population_version,
            "owner": ledger.owner,
            "gate": gate,
            "health": health_verdict,
            "previous_preserved": previous_preserved,
        },
        "checkpoint": {
            "version": checkpoint_version,
            "owner": checkpoint_owner,
            "advanced": checkpoint_advanced,
            "action": checkpoint_action,
            "oldest_tail_required": oldest_tail_required,
            "oldest_tail_reached": oldest_tail_reached,
        },
        "health": {
            "artifact_fresh": artifact_fresh,
            "artifact_generation": health_generation,
            "verdict": health_verdict,
            "invocation_success_only": False,
        },
        **({"cancellation": cancellation} if cancellation else {}),
    }


def terminal_for(
    *,
    all_required_done: bool,
    published: bool,
    error: bool = False,
    cancelled: bool = False,
    overlap_refused: bool = False,
) -> str:
    """complete | partial | failed | cancelled | overlap_refused.

    ``complete`` is the hard one to earn: every required phase done AND the
    artifact actually published. Compute completion is not publication, and a
    run that computed everything but could not persist it is not complete.
    """
    if overlap_refused:
        return TERMINAL_OVERLAP_REFUSED
    if cancelled:
        return TERMINAL_CANCELLED
    if error:
        return TERMINAL_FAILED
    if all_required_done and published:
        return TERMINAL_COMPLETE
    return TERMINAL_PARTIAL


def health_for(
    *,
    terminal: str,
    ledger_write: str,
    artifact_fresh: bool,
    artifact_generation: Optional[int],
) -> str:
    """GREEN is earned, never assumed.

    A ledger write failure makes progress UNKNOWN, never GREEN (Queue 300M
    Item 0's closing sentence): a run whose own telemetry did not persist
    cannot vouch for what it did. A stale artifact is likewise never GREEN —
    health is about the ARTIFACT's generation, not the invocation.
    """
    if ledger_write != "ok":
        return UNKNOWN
    if terminal in (TERMINAL_FAILED, TERMINAL_HARD_LOSS):
        return RED
    if terminal == TERMINAL_COMPLETE and artifact_fresh and artifact_generation is not None:
        return GREEN
    return UNKNOWN


# =============================================================================
# Checkpoint
# =============================================================================


def input_fingerprint(*parts: str) -> str:
    """Stable fingerprint of everything a carried phase output depends on.

    Any change to the population version or to the SQL of the phases themselves
    must invalidate carried output — resuming a phase whose query has changed
    would publish a payload half-built by the old code and half by the new,
    which is worse than recomputing.
    """
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()[:32]


@dataclass(frozen=True)
class MainBuildCheckpoint:
    """What a prior beat proved it had, and who is allowed to advance it."""

    version: str
    generation: int = 0
    owner: str = ""
    lease_expires_at: float = 0.0
    input_fingerprint: str = ""
    completed_phases: tuple[str, ...] = ()
    phase_outputs: dict[str, Any] = field(default_factory=dict)
    terminal: str = TERMINAL_PARTIAL

    def has(self, phase: str) -> bool:
        return phase in self.completed_phases and phase in self.phase_outputs

    def output(self, phase: str) -> Optional[dict[str, Any]]:
        if not self.has(phase):
            return None
        stored = self.phase_outputs.get(phase)
        return stored if isinstance(stored, dict) else None

    def with_phase(
        self, phase: str, output: dict[str, Any], *, owner: str, lease_expires_at: float
    ) -> "MainBuildCheckpoint":
        return replace(
            self,
            owner=owner,
            lease_expires_at=lease_expires_at,
            completed_phases=tuple(
                list(self.completed_phases) + ([phase] if phase not in self.completed_phases else [])
            ),
            phase_outputs={**self.phase_outputs, phase: output},
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": MAIN_CHECKPOINT_SCHEMA,
            "task": MAIN_BUILD_TASK,
            "version": self.version,
            "generation": self.generation,
            "owner": self.owner,
            "lease_expires_at": self.lease_expires_at,
            "input_fingerprint": self.input_fingerprint,
            "completed_phases": list(self.completed_phases),
            "phase_outputs": self.phase_outputs,
            "terminal": self.terminal,
        }


def new_main_checkpoint(
    *, version: str, fingerprint: str, owner: str, generation: int
) -> MainBuildCheckpoint:
    return MainBuildCheckpoint(
        version=version,
        generation=generation,
        owner=owner,
        input_fingerprint=fingerprint,
    )


def _stored_output_is_whole(phase: str, stored: Any) -> bool:
    """A carried phase output is usable only if EVERY key it owes is present."""
    if not isinstance(stored, dict) or stored.get("stored") is not True:
        return False
    values = stored.get("values")
    if not isinstance(values, dict):
        return False
    return set(values) == set(PHASE_OUTPUT_KEYS.get(phase, frozenset()))


def decode_main_checkpoint(
    raw: Any,
    *,
    expected_version: str,
    expected_fingerprint: str,
    owner: str,
    generation: int,
    now: float,
) -> tuple[MainBuildCheckpoint, str]:
    """Load a persisted checkpoint, refusing anything not provably resumable.

    Returns ``(checkpoint, action)``. The actions, and why each exists:

    * ``fresh`` — nothing there. Start over; that is not an error.
    * ``invalidate`` — something is there but we cannot vouch for it: wrong
      schema, wrong task, wrong population version, wrong input fingerprint,
      malformed shape. Resuming a checkpoint you cannot vouch for skips work
      while claiming to have done it, so it is discarded and rebuilt.
    * ``refuse`` — a DIFFERENT owner holds an unexpired lease. Another beat is
      mid-build; running a second one against the same checkpoint is how two
      workers each advance half of it. Doing nothing is the correct behaviour.
    * ``resume`` — same population, same inputs, lease ours or expired. Carry
      the committed phases forward.
    """
    blank = new_main_checkpoint(
        version=expected_version,
        fingerprint=expected_fingerprint,
        owner=owner,
        generation=generation,
    )
    if raw is None:
        return blank, FRESH
    if not isinstance(raw, dict):
        return blank, INVALIDATE
    if raw.get("schema") != MAIN_CHECKPOINT_SCHEMA or raw.get("task") != MAIN_BUILD_TASK:
        return blank, INVALIDATE
    if raw.get("version") != expected_version:
        # The population moved under us. Every phase must be recomputed.
        return blank, INVALIDATE
    if raw.get("input_fingerprint") != expected_fingerprint:
        # The queries themselves changed. Carried output is from a different build.
        return blank, INVALIDATE

    held_by = raw.get("owner") or ""
    lease = raw.get("lease_expires_at")
    lease_expires_at = float(lease) if isinstance(lease, (int, float)) and not isinstance(lease, bool) else 0.0
    if held_by and held_by != owner and lease_expires_at > now:
        return (
            replace(blank, owner=held_by, lease_expires_at=lease_expires_at),
            REFUSE,
        )

    completed = raw.get("completed_phases")
    outputs = raw.get("phase_outputs")
    if not isinstance(completed, list) or not isinstance(outputs, dict):
        return blank, INVALIDATE

    # Only phases that are BOTH declared complete and carry a COMPLETE stored
    # output can be resumed. A phase recorded complete with no output — or with
    # a partial one — is a bookkeeping error, and treating it as done would
    # silently drop its data from the published payload.
    resumable = tuple(
        name
        for name in completed
        if isinstance(name, str)
        and name in RESUMABLE_PHASES
        and _stored_output_is_whole(name, outputs.get(name))
    )
    return (
        MainBuildCheckpoint(
            version=expected_version,
            generation=generation,
            owner=owner,
            lease_expires_at=lease_expires_at,
            input_fingerprint=expected_fingerprint,
            completed_phases=resumable,
            phase_outputs={name: outputs[name] for name in resumable},
            terminal=str(raw.get("terminal") or TERMINAL_PARTIAL),
        ),
        RESUME if resumable else FRESH,
    )
