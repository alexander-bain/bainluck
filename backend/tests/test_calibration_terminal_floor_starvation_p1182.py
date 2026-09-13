"""CAL-P1182 / #5963 — a terminal phase's floor is not a fact about itself.

The production row these tests pin, read from ``calibration:main:phase_ledger``
on 2026-09-13 at 17:46:28Z, nine hours into a q271 rebuild that had banked 26 of
128 units and was serving ``503 no_trustworthy_snapshot`` on ``/api/calibration``:

    phase                     budget_ms     floor_ms   slack_assigned_ms
    futures                     124,827    1,196,786                   0
    sports                       46,100       15,418                   0
    diagnostics                  99,815           23                   0
    aggregate                       144         None                   0
    serialize_gate_publish    1,109,114    1,199,178           1,108,547

    staged:unit_bound_ms:futures            112,345
    staged:unit_bound_headroom_ms:futures   988,009
    plan.futures.unit_ms                    110,316
    plan.futures.unit_ms_worst              339,184

Two phases qualified as truncating. ``serialize_gate_publish``'s floor beat
``futures``'s by **2,392 ms**, so the largest-floor rule handed it every one of
the 1,108,547 unallocated milliseconds — and it cannot spend them: its pre-slack
budget is 567 ms, which is ``max(observed) * BUDGET_SAFETY`` over ten completions
whose worst was 378 ms. Its floor is **3,172x its own worst completion**, because
it runs last, consumes every other phase's output, and is therefore killed by the
BEAT deadline whenever ``futures`` overruns. The floor measures the upstream's
overrun, not its own cost.

Meanwhile the phase that was starving kept a 124,827 ms budget, which
``_statement_timeout_for`` turns into the 112,345 ms fence above — and 23 of the
24 durations in ``unit_worst_history`` exceed it. The CAL-P163 unit fence was
working correctly and asking for ``max(110,316 x 4.0, 339,184 x 1.5)`` =
508,776 ms; ``min(phase_bound, unit_bound)`` clamped it to the starved phase
budget. Nothing expensive could ever bank, at any number of beats.

And it is a one-way ratchet: every starved beat raises the inherited floor, which
keeps the terminal phase ahead of the phase that is actually starving, which
sends it the slack again.

These tests are written against the production row, not a tidy fixture, and the
fence assertions drive ``PhaseLedger.statement_timeout_for_unit`` itself rather
than re-deriving its arithmetic — a bound re-implemented in its own test is a
bound nobody checked.
"""

from __future__ import annotations

from dataclasses import replace

from app.utils.calibration_phase_ledger import (
    _statement_timeout_for,
    BUDGET_BASIS_MEASURED,
    BUDGET_BASIS_PLUS_SLACK,
    CLEANUP_MARGIN_MS,
    PHASE_FUTURES,
    PHASE_PUBLISH,
    RESUMABLE_PHASES,
    SOFT_LIMIT_MS,
    PhaseLedger,
    bottleneck_phase,
    derive_plan,
)

# --- The production row ------------------------------------------------------

# Back-derived from the budgets above: ``derive_plan`` budgets a phase at
# ``max(observed) * BUDGET_SAFETY``, so one completion at budget/1.5 reproduces
# the deployed plan exactly. Asserted in the first test rather than assumed.
PROD_HISTORY: dict[str, list[int]] = {
    "futures": [83_218],
    "sports": [30_733],
    "diagnostics": [66_543],
    "aggregate": [96],
    "serialize_gate_publish": [378],
}
PROD_FLOORS: dict[str, list[int]] = {
    "futures": [1_196_786],
    "sports": [15_418],
    "diagnostics": [23],
    "serialize_gate_publish": [1_199_178],
}
PROD_UNITS: dict[str, dict[str, int]] = {
    "futures": {
        "unit_ms": 110_316,
        "units_total": 128,
        "units_done": 26,
        "unit_ms_worst": 339_184,
    }
}

PROD_FENCE_MS = 112_345  # staged:unit_bound_ms:futures, as deployed
PROD_WORST_UNIT_MS = 339_184


def _prod_plan():
    return derive_plan(PROD_HISTORY, floors=PROD_FLOORS, unit_costs=PROD_UNITS)


def _deployed_plan():
    """The 17:46Z plan as production actually recorded it, slack on publish.

    Rebuilt by moving the slack back rather than by reviving the old selector:
    the point of comparison is the deployed BUDGETS, which are a recorded fact,
    and a test that re-implements the rule it is grading grades nothing.
    """
    plan = _prod_plan()
    moved = []
    for b in plan.budgets:
        if b.name == PHASE_FUTURES:
            starved = b.budget_ms - b.slack_assigned_ms
            b = replace(
                b,
                budget_ms=starved,
                statement_timeout_ms=_statement_timeout_for(starved),
                budget_basis=BUDGET_BASIS_MEASURED,
                slack_assigned_ms=0,
            )
        elif b.name == PHASE_PUBLISH:
            b = replace(
                b,
                budget_ms=1_109_114,
                statement_timeout_ms=_statement_timeout_for(1_109_114),
                budget_basis=BUDGET_BASIS_PLUS_SLACK,
                slack_assigned_ms=1_108_547,
            )
        moved.append(b)
    return replace(plan, budgets=tuple(moved))


def _ledger(plan) -> PhaseLedger:
    return PhaseLedger(
        plan=plan,
        population_version="q271",
        owner="test",
        generation=1_789_000_000_000,
        input_fingerprint="cal-p1182",
    )


# --- 1. The rig reproduces the deployed plan ---------------------------------


def test_the_inputs_reproduce_the_deployed_budgets():
    """Without this the rest of the file grades a fixture, not the outage.

    Also pins the two numbers the defect turns on: the terminal phase's floor
    really does beat the starving phase's, so the largest-floor rule really
    would pick it. A guard whose premise has quietly stopped holding passes for
    the wrong reason.
    """
    full = _prod_plan()

    def pre_slack(name: str) -> int:
        b = full.by_name(name)
        return b.budget_ms - b.slack_assigned_ms

    assert pre_slack(PHASE_FUTURES) == 124_827
    assert pre_slack("sports") == 46_100
    assert pre_slack("diagnostics") == 99_815
    assert pre_slack("aggregate") == 144

    publish = full.by_name(PHASE_PUBLISH)
    # 567 ms of measured cost, carrying a floor three thousand times larger.
    assert publish.budget_ms - publish.slack_assigned_ms == 567
    assert publish.floor_ms == 1_199_178
    assert publish.floor_ms > full.by_name(PHASE_FUTURES).floor_ms
    assert publish.floor_ms - full.by_name(PHASE_FUTURES).floor_ms == 2_392


# --- 2. The repair: the slack goes to the phase that can spend it ------------


def test_the_window_slack_goes_to_futures_not_to_the_terminal_phase():
    plan = _prod_plan()
    assert plan.slack_target == PHASE_FUTURES
    assert plan.by_name(PHASE_FUTURES).budget_basis == BUDGET_BASIS_PLUS_SLACK
    assert plan.by_name(PHASE_FUTURES).slack_assigned_ms == 1_108_547
    assert plan.by_name(PHASE_PUBLISH).slack_assigned_ms == 0
    assert plan.by_name(PHASE_PUBLISH).budget_basis == BUDGET_BASIS_MEASURED


def test_the_fence_stops_being_the_phase_budget_and_the_worst_unit_can_bank():
    """The ship, stated as the reader sees it: expensive units start banking.

    Driven through ``statement_timeout_for_unit`` — the same call that wrote
    ``staged:unit_bound_ms:futures`` = 112,345 in production.
    """
    deployed = _ledger(_deployed_plan())
    deployed_fence = deployed.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
    assert deployed_fence == PROD_FENCE_MS
    assert deployed_fence < PROD_WORST_UNIT_MS  # nothing expensive could bank

    repaired = _ledger(_prod_plan())
    fence = repaired.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
    assert fence > PROD_WORST_UNIT_MS
    assert fence > deployed_fence


def test_the_fence_is_still_a_measured_limit_not_an_open_window():
    """"Do not merely remove all time limits" — the unit bound now BINDS.

    After the repair the phase budget stops being the clamp and the CAL-P163
    unit bound takes over: ``max(unit_mean x 4.0, unit_worst x 1.5)``, which is
    derived entirely from completed durations. The fence is strictly smaller
    than the phase's own statement timeout, so it is doing real work.
    """
    plan = _prod_plan()
    ledger = _ledger(plan)
    fence = ledger.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
    phase_bound = ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=0)
    assert fence < phase_bound
    # A unit is still bounded by a multiple of what units have been observed to
    # cost, so a runaway unit is cancelled exactly as before.
    assert fence < PROD_WORST_UNIT_MS * 2


# --- 3. Finalization keeps its time ------------------------------------------


def test_the_terminal_phase_keeps_its_full_measured_budget():
    """Widening futures must not be paid for out of the publish tail."""
    plan = _prod_plan()
    publish = plan.by_name(PHASE_PUBLISH)
    # max(observed) * BUDGET_SAFETY over its ten completions — the full measured
    # allotment, undiminished by the phase that took the slack.
    assert publish.budget_ms == 567
    assert publish.budget_ms == _deployed_plan().by_name(PHASE_PUBLISH).budget_ms - 1_108_547
    assert publish.statement_timeout_ms < publish.budget_ms


def test_the_cleanup_margin_survives_and_the_plan_stays_inside_the_soft_limit():
    plan = _prod_plan()
    assert plan.declared_ms <= plan.available_ms
    assert plan.available_ms == SOFT_LIMIT_MS - CLEANUP_MARGIN_MS
    # The publish tail's reservation is outside the window and untouched.
    assert plan.declared_ms + CLEANUP_MARGIN_MS <= SOFT_LIMIT_MS
    for budget in plan.budgets:
        assert budget.statement_timeout_ms < budget.budget_ms


# --- 4. Committed chunks survive and resume ----------------------------------


def test_banked_units_are_carried_and_the_widened_phase_is_the_resumable_one():
    """The 26 already-banked units are not at risk from this change.

    ``futures`` is the phase a later beat can carry forward, so a budget change
    costs it UNITS, never the beat; and the plan still reports the cursor it was
    handed, so the next beat resumes from 26 rather than restarting.
    """
    plan = _prod_plan()
    assert PHASE_FUTURES in RESUMABLE_PHASES
    assert PHASE_PUBLISH not in RESUMABLE_PHASES
    futures = plan.by_name(PHASE_FUTURES)
    assert futures.units_done == 26
    assert futures.units_total == 128
    assert futures.unit_ms == 110_316
    assert futures.unit_ms_worst == 339_184


# --- 5. The rule is conditional, not a phase-name exclusion ------------------


def test_a_terminal_phase_truncating_alone_still_wins_the_slack():
    """No upstream explanation for its floor ⇒ the floor is its own evidence.

    This is why the repair is conditional. A flat "publish never gets slack"
    would be a constant about a phase name, and would strand a genuinely slow
    publish forever.
    """
    plan = derive_plan(
        {"futures": [50_000], "serialize_gate_publish": [400]},
        floors={"serialize_gate_publish": [900_000]},
        phases=(PHASE_FUTURES, PHASE_PUBLISH),
    )
    assert plan.slack_target == PHASE_PUBLISH
    assert plan.by_name(PHASE_PUBLISH).budget_basis == BUDGET_BASIS_PLUS_SLACK


def test_among_resumable_phases_the_largest_floor_still_wins():
    """The CAL-P072 rule is untouched where no terminal phase is involved."""
    plan = derive_plan(
        {"futures": [100_000], "diagnostics": [100_000]},
        floors={"futures": [200_000], "diagnostics": [800_000]},
        phases=("futures", "diagnostics"),
    )
    assert plan.slack_target == "diagnostics"


def test_no_truncation_anywhere_still_allocates_nothing():
    plan = derive_plan(
        {"futures": [50_000], "serialize_gate_publish": [400]},
        phases=(PHASE_FUTURES, PHASE_PUBLISH),
    )
    assert plan.slack_target is None
    assert bottleneck_phase(plan.budgets) is None


# --- 6. The ratchet is broken ------------------------------------------------


def test_an_unboundedly_growing_inherited_floor_never_recaptures_the_slack():
    """The failure was self-sustaining; the fix must not merely out-race it.

    Each starved beat cancels the terminal phase later, so its floor climbs
    without limit. Under the old rule that guaranteed it the slack forever. Here
    it loses at every size, because it loses on the partition, not on magnitude.
    """
    for inherited_floor in (1_199_178, 2_000_000, 50_000_000):
        plan = derive_plan(
            PROD_HISTORY,
            floors={**PROD_FLOORS, PHASE_PUBLISH: [inherited_floor]},
            unit_costs=PROD_UNITS,
        )
        assert plan.slack_target == PHASE_FUTURES, inherited_floor
        assert plan.by_name(PHASE_PUBLISH).slack_assigned_ms == 0, inherited_floor
