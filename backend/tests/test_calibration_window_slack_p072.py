"""CAL-P072 / ruling 089 — the beat's unallocated time goes to the starving phase.

The attribution these tests exist to pin, read end-to-end from the producer's own
durable ledger row (``calibration:main:phase_ledger``) on 2026-08-18, beat
generation ``1787091300309`` (dispatched 22:15:00Z, terminal written 22:19:12Z):

    stage_counts    read:futures_generation 1, read:futures_unit 1
    stages          read:futures_generation  72,767 ms
                    read:futures_unit       159,801 ms   <- cancelled
                    staged:units_this_beat        1
                    staged:units_completed_this_beat  0
                    staged:units_banked           3  (of 128)
    plan[futures]   budget_ms 177,374   statement_timeout_ms 159,637
    terminal        failed          checkpoint_write  nothing_to_bank

and, from ``/api/admin/task-metrics?task=precompute_calibration_main``:

    last_verdict         thrown
    last_verdict_reason  DBAPIError
    last_error           asyncpg.exceptions.QueryCanceledError:
                         canceling statement due to statement timeout
                         [SQL: WITH market_info AS ( ...

**The failure mode is a TIMEOUT, and the clock that fired is ours.** 159,801 ms
of measured unit read against a 159,637 ms statement timeout we set ourselves is
a 164 ms overhead gap — the cancellation is attributed to the plan's own derived
cap, not to Celery, not to the broker, not to an exception in build logic, and
not to a silent skip. One unit was attempted, zero completed, nothing banked,
for the 111th consecutive beat.

And the cap cannot be corrected by the thing it caps: a cancelled phase records
a FLOOR, and ``derive_plan`` forbids a floor from producing a budget. So the
budget stays pinned to ten pre-q268 completions while every new failure raises a
floor the budget is not allowed to read. Ruling 089 breaks that from outside it
by handing the phase the ~72% of the beat that no phase's measurement claimed.

These tests are deliberately written against the PRODUCTION ROW rather than a
tidy fixture. A budget rule graded only on round numbers is graded on the case
that was never going to fail.
"""

from __future__ import annotations

import pytest

from app.utils.calibration_phase_ledger import (
    BUDGET_BASIS_MEASURED,
    BUDGET_BASIS_PLUS_SLACK,
    BUDGET_BASIS_SCALED_DOWN,
    BUDGET_BASIS_UNMEASURED,
    CLEANUP_MARGIN_MS,
    PHASE_FUTURES,
    SOFT_LIMIT_MS,
    STATEMENT_INNER_MARGIN_MS,
    bottleneck_phase,
    derive_plan,
)

# --- The production row ------------------------------------------------------

PROD_HISTORY: dict[str, list[int]] = {
    "sports": [5014, 2534, 6628, 2336, 2634, 8384, 3481, 3011, 2277, 7003],
    "futures": [79516, 52739, 111832, 48683, 47389, 111287, 53598, 111361, 118249, 103756],
    "aggregate": [45, 47, 45, 67, 65, 49, 48, 46, 70, 50],
    "diagnostics": [108639, 119051, 84612, 75493, 77447, 128056, 107245, 55294, 46616, 83894],
}
PROD_FLOORS: dict[str, list[int]] = {
    "futures": [1322901, 1155129, 1066278, 1141606, 371107, 443972, 236038, 218026, 256281, 251046],
    "serialize_gate_publish": [1973, 1856, 1644, 2097, 1933, 2342, 1958, 1803, 1761, 1754],
}

#: What the deployed plan gave the futures phase, and what the beat measured
#: against it. Both are readings, not choices.
DEPLOYED_FUTURES_BUDGET_MS = 177_374
DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS = 159_637
OBSERVED_CANCELLED_UNIT_READ_MS = 159_801
DEPLOYED_DECLARED_MS = 382_139

#: The SECOND failed beat, generation ``1787094900158`` (23:15:00Z, terminal
#: 23:20:16Z), read live one hour after the first. It is the reproduction the
#: ruling asked for, and it is a better specimen than the first because it
#: contains BOTH outcomes under one cap:
#:
#:     staged:units_this_beat            2
#:     staged:units_completed_this_beat  1
#:     staged:unit_ms_mean_completed   103,473 ms   <- unit 1, finished
#:     read:futures_unit               263,240 ms   <- both units together
#:     staged:units_banked                   4      (3 -> 4)
#:     terminal                         failed
#:
#: so the cancelled second unit ran ``263,240 - 103,473 = 159,767 ms`` against
#: the same 159,637 ms cap — 130 ms of overhead, the same signature as the
#: 22:15Z beat's 164 ms.
#:
#: **And it settles what the first beat could not.** Units are not uniformly
#: over the cap: one finished at 103.5 s. So the build is not merely slow, it is
#: SORTED — every unit under ~160 s banks, every unit over it never can, and no
#: number of beats changes which side a unit falls on. The stall is permanent,
#: not gradual, and only moving the cap moves a unit across it.
SECOND_BEAT_UNITS_ATTEMPTED = 2
SECOND_BEAT_UNITS_COMPLETED = 1
SECOND_BEAT_COMPLETED_UNIT_MS = 103_473
SECOND_BEAT_TOTAL_UNIT_READ_MS = 263_240


def _prod_plan():
    return derive_plan(PROD_HISTORY, floors=PROD_FLOORS)


# --- 1. The attribution itself ----------------------------------------------


def test_the_deployed_cap_is_what_cancelled_the_unit():
    """The cancel point IS the plan's number, to 164 ms of overhead.

    This is the whole basis for treating the budget as the lever. If the unit
    had been cancelled anywhere else — the deadline bound, a Celery limit, a
    server-side ``statement_timeout`` we did not set — widening the phase budget
    would be hygiene aimed at the wrong clock.
    """
    plan = derive_plan(PROD_HISTORY, floors=PROD_FLOORS)
    futures = plan.by_name(PHASE_FUTURES)
    assert futures is not None

    # The measured budget the deployed code derived, reproduced exactly.
    measured_budget = futures.budget_ms - futures.slack_assigned_ms
    assert measured_budget == DEPLOYED_FUTURES_BUDGET_MS

    # ...and the cap it implies, which is the number Postgres enforced.
    from app.utils.calibration_phase_ledger import _statement_timeout_for

    assert _statement_timeout_for(measured_budget) == DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS

    overhead_ms = OBSERVED_CANCELLED_UNIT_READ_MS - DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS
    assert 0 < overhead_ms < 1_000, (
        "the observed unit read must sit just past our own statement timeout — "
        f"got {overhead_ms} ms of gap, which is too large to call the cancel ours"
    )


def test_the_mechanism_reproduces_on_a_second_failed_beat():
    """Same cap, same signature, one hour later — and a completed unit beside it.

    The reproduction requirement, discharged arithmetically rather than by
    assertion. Two independent beats, two cancelled reads, both landing a
    sub-200 ms overhead past the SAME derived cap.
    """
    cancelled_read_ms = SECOND_BEAT_TOTAL_UNIT_READ_MS - SECOND_BEAT_COMPLETED_UNIT_MS
    assert cancelled_read_ms == 159_767
    for observed in (OBSERVED_CANCELLED_UNIT_READ_MS, cancelled_read_ms):
        overhead = observed - DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS
        assert 0 < overhead < 1_000, f"{observed} ms is not our cap firing"

    # The finding the second beat adds: the population straddles the cap.
    assert SECOND_BEAT_COMPLETED_UNIT_MS < DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS
    assert cancelled_read_ms >= DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS


def test_a_unit_that_straddles_the_cap_is_a_permanent_stall_not_a_slow_one():
    """Under the deployed cap the expensive units are unreachable at any beat count.

    This is why "give it more beats" was never going to work, and why the
    out-of-band beat CAL-P071 dispatched banked nothing: the cheap units drain,
    and then every remaining beat re-attempts a unit that cannot fit.
    """
    plan = _prod_plan()
    futures = plan.by_name(PHASE_FUTURES)
    measured_cap = DEPLOYED_FUTURES_STATEMENT_TIMEOUT_MS
    cancelled_unit_lower_bound = SECOND_BEAT_TOTAL_UNIT_READ_MS - SECOND_BEAT_COMPLETED_UNIT_MS

    assert cancelled_unit_lower_bound > measured_cap  # unreachable, forever
    assert cancelled_unit_lower_bound < futures.statement_timeout_ms  # reachable now

    # A cancelled unit is a lower bound, so headroom is the honest thing to
    # report: we know the unit needs MORE than 159,767 ms, not how much more.
    headroom = futures.statement_timeout_ms - cancelled_unit_lower_bound
    assert headroom > 900_000


def test_the_measured_budget_is_a_ratchet_that_only_a_reallocation_breaks():
    """Every recorded floor exceeds the budget, and no floor may raise it.

    Ten floors, all above 177,374 ms, and the budget is unmoved by all ten. That
    is the loop: the phase is cancelled, records evidence it needed more, and
    the rule that reads evidence is forbidden (correctly) from reading THIS kind
    of evidence, because a truncated run is a lower bound and not a cost.
    """
    measured_only = derive_plan(PROD_HISTORY, floors=PROD_FLOORS)
    futures = measured_only.by_name(PHASE_FUTURES)
    measured_budget = futures.budget_ms - futures.slack_assigned_ms
    assert all(f > measured_budget for f in PROD_FLOORS["futures"]), (
        "specimen precondition: every floor is above the budget derived beside it"
    )
    # And with the floors removed entirely the measured budget is identical —
    # proving the floors contributed nothing to it.
    without_floors = derive_plan(PROD_HISTORY)
    assert without_floors.by_name(PHASE_FUTURES).budget_ms == measured_budget


# --- 2. What the reallocation does ------------------------------------------


def test_production_row_gets_the_unallocated_window():
    plan = _prod_plan()
    futures = plan.by_name(PHASE_FUTURES)

    assert futures.budget_basis == BUDGET_BASIS_PLUS_SLACK
    assert futures.slack_assigned_ms > 0
    assert futures.budget_ms == 1_172_893
    assert futures.statement_timeout_ms == 1_142_893

    # The point of the exercise: the unit that was cancelled now has room.
    assert futures.statement_timeout_ms > OBSERVED_CANCELLED_UNIT_READ_MS
    # And so does the whole beat's measured work — the 72.8 s generation read
    # plus a unit at the floor it was cancelled on.
    assert futures.statement_timeout_ms > 72_767 + OBSERVED_CANCELLED_UNIT_READ_MS


def test_the_deployed_plan_really_was_leaving_most_of_the_beat_unspent():
    """~72% unallocated, reproduced from the row rather than quoted from it."""
    before = sum(
        b.budget_ms - b.slack_assigned_ms
        for b in _prod_plan().budgets
        if b.budget_ms is not None
    )
    assert before == DEPLOYED_DECLARED_MS
    unallocated = _prod_plan().available_ms - before
    assert unallocated / _prod_plan().available_ms > 0.70


def test_no_other_phase_loses_anything():
    before = derive_plan(PROD_HISTORY)  # no floors -> nothing qualifies, no slack
    after = _prod_plan()
    for name in ("sports", "diagnostics", "aggregate"):
        b, a = before.by_name(name), after.by_name(name)
        assert b.budget_ms == a.budget_ms
        assert b.statement_timeout_ms == a.statement_timeout_ms
        assert a.budget_basis == BUDGET_BASIS_MEASURED
        assert a.slack_assigned_ms == 0


def test_the_measured_number_stays_recoverable():
    """``budget_ms - slack_assigned_ms`` is the measurement, unmodified.

    A reallocated budget is not a cost, and a reader who needs the cost must be
    able to get it back without re-deriving the plan.
    """
    futures = _prod_plan().by_name(PHASE_FUTURES)
    assert futures.budget_ms - futures.slack_assigned_ms == DEPLOYED_FUTURES_BUDGET_MS
    assert futures.as_payload()["budget_basis"] == BUDGET_BASIS_PLUS_SLACK
    assert futures.as_payload()["slack_assigned_ms"] == futures.slack_assigned_ms


# --- 3. The bound -----------------------------------------------------------


def test_declared_total_reaches_the_ceiling_and_never_passes_it():
    plan = _prod_plan()
    assert plan.declared_ms <= plan.available_ms
    assert plan.declared_ms + plan.cleanup_margin_ms <= plan.soft_limit_ms
    # It should genuinely reach the ceiling — a reallocation that leaves the
    # window half unspent has not done the thing it was ruled to do.
    assert plan.declared_ms >= plan.available_ms - 5_000


def test_an_unmeasured_phase_keeps_its_floor_as_a_reserve():
    """``serialize_gate_publish`` declares nothing, so reserve its lower bound."""
    plan = _prod_plan()
    publish = plan.by_name("serialize_gate_publish")
    assert publish.budget_ms is None
    assert publish.budget_basis == BUDGET_BASIS_UNMEASURED
    reserve = max(PROD_FLOORS["serialize_gate_publish"])
    assert plan.declared_ms + reserve == plan.available_ms


def test_an_unmeasured_phase_is_never_the_bottleneck():
    """Even with a floor of its own, a phase with no measured budget gets nothing.

    Its cost is unknown in BOTH directions, so handing it the window would be a
    guess wearing an allocation's clothes. It is reserved for, not allocated to.
    """
    history = {"futures": [100_000], "sports": [1_000]}
    floors = {"serialize_gate_publish": [40_000], "futures": [900_000]}
    plan = derive_plan(
        history,
        floors=floors,
        phases=("futures", "sports", "serialize_gate_publish"),
    )
    assert plan.slack_target == PHASE_FUTURES
    assert plan.by_name("serialize_gate_publish").budget_ms is None
    assert plan.by_name("serialize_gate_publish").slack_assigned_ms == 0
    assert plan.declared_ms + 40_000 == plan.available_ms


def test_an_unmeasured_phase_large_enough_to_eat_the_window_suppresses_the_handout():
    """No slack exists once the unmeasured reserve consumes it, so none is given.

    A reserve is not a leftover. If the only phase we have never measured to
    completion has already been seen running for most of a beat, the window is
    not free and the reallocation must decline rather than overcommit it.
    """
    plan = derive_plan(
        {"futures": [100_000], "sports": [1_000]},
        floors={"serialize_gate_publish": [1_300_000], "futures": [900_000]},
        phases=("futures", "sports", "serialize_gate_publish"),
    )
    assert plan.slack_target is None
    assert plan.by_name(PHASE_FUTURES).budget_basis == BUDGET_BASIS_MEASURED
    assert plan.declared_ms <= plan.available_ms


# --- 4. When it must NOT fire -----------------------------------------------


def test_no_truncation_evidence_means_no_reallocation():
    """Slack stays unallocated when nothing has been observed to be starved.

    A plan with no floor has no basis for naming a bottleneck, and picking one
    anyway would be exactly the invented constant this module refuses to write.
    """
    plan = derive_plan({"futures": [50_000], "sports": [1_000]}, phases=("futures", "sports"))
    assert bottleneck_phase(plan.budgets) is None
    for b in plan.budgets:
        assert b.budget_basis == BUDGET_BASIS_MEASURED
        assert b.slack_assigned_ms == 0
    assert plan.declared_ms < plan.available_ms


def test_a_floor_inside_its_own_budget_is_not_truncation_evidence():
    """The phase ran long and stopped — but never past what it was allowed.

    Whatever stopped it, the budget was not the binding constraint, so widening
    the budget is not the fix and this rule must not claim it is.
    """
    plan = derive_plan(
        {"futures": [100_000], "sports": [1_000]},
        floors={"futures": [90_000]},  # 90,000 < 150,000 budget
        phases=("futures", "sports"),
    )
    assert plan.by_name(PHASE_FUTURES).floor_ms == 90_000
    assert bottleneck_phase(plan.budgets) is None
    assert plan.by_name(PHASE_FUTURES).budget_basis == BUDGET_BASIS_MEASURED


def test_scaled_down_plans_are_untouched():
    """Over-declared plans have no slack, and the scale-down path is unchanged."""
    plan = derive_plan(
        {"futures": [1_000_000], "sports": [1_000_000]},
        floors={"futures": [1_400_000]},
        phases=("futures", "sports"),
    )
    assert plan.declared_ms <= plan.available_ms
    for b in plan.budgets:
        assert b.budget_basis == BUDGET_BASIS_SCALED_DOWN
        assert b.slack_assigned_ms == 0


# --- 5. The bottleneck is chosen by evidence, not by name -------------------


def test_bottleneck_is_the_largest_floor_over_its_own_budget():
    """``futures`` appears nowhere in the rule; swap the evidence, swap the winner."""
    plan = derive_plan(
        {"futures": [100_000], "diagnostics": [100_000]},
        floors={"futures": [200_000], "diagnostics": [800_000]},
        phases=("futures", "diagnostics"),
    )
    assert plan.slack_target == "diagnostics"
    assert plan.by_name("diagnostics").budget_basis == BUDGET_BASIS_PLUS_SLACK
    assert plan.by_name(PHASE_FUTURES).budget_basis == BUDGET_BASIS_MEASURED


def test_a_finished_plan_reports_its_own_choice_not_a_re_derived_one():
    """``slack_target`` is the record; ``bottleneck_phase`` re-run names the runner-up.

    Found by the test above before this shipped. Widening the winner's budget
    puts its floor back inside it, so the winner stops qualifying and the
    selector — asked again, over its own output — answers with whoever is now
    the most starved. A plan must report the decision it made, not re-take it.
    """
    plan = derive_plan(
        {"futures": [100_000], "diagnostics": [100_000]},
        floors={"futures": [200_000], "diagnostics": [800_000]},
        phases=("futures", "diagnostics"),
    )
    assert plan.slack_target == "diagnostics"
    assert bottleneck_phase(plan.budgets) == PHASE_FUTURES  # the runner-up
    assert plan.by_name("diagnostics").floor_ms < plan.by_name("diagnostics").budget_ms
    assert plan.as_payload()["slack_target"] == "diagnostics"
    assert plan.as_payload()["unallocated_ms"] == 0


def test_exactly_one_phase_is_ever_widened():
    plan = derive_plan(
        {"futures": [100_000], "diagnostics": [100_000], "sports": [1_000]},
        floors={"futures": [900_000], "diagnostics": [800_000]},
        phases=("futures", "diagnostics", "sports"),
    )
    widened = [b for b in plan.budgets if b.slack_assigned_ms]
    assert [b.name for b in widened] == [PHASE_FUTURES]


# --- 6. Composition with the CAL-P071 ETA -----------------------------------


def test_the_eta_divides_by_the_widened_allotment():
    """CAL-P071 made the divisor the phase's own budget; 089 makes that budget real.

    The two fixes only pay out together: dividing by the true allotment is what
    made the ETA honest, and widening the allotment is what makes the honest
    number small enough to matter.
    """
    plan = derive_plan(
        PROD_HISTORY,
        floors=PROD_FLOORS,
        unit_costs={PHASE_FUTURES: {"unit_ms": 126_958, "units_total": 128, "units_done": 3}},
    )
    projection = plan.unit_projection(PHASE_FUTURES)
    assert projection["per_beat_basis"] == "phase_budget"
    assert projection["per_beat_ms"] == plan.by_name(PHASE_FUTURES).budget_ms
    # Same unit cost, same 125 remaining units. Before: 1 per beat, 125 beats.
    assert DEPLOYED_FUTURES_BUDGET_MS // 126_958 == 1
    assert projection["units_per_beat"] == 9
    assert projection["beats_remaining"] == 14


@pytest.mark.parametrize("budget_ms", [1, 100, 300_000, 1_172_893, 1_380_000])
def test_statement_timeout_stays_strictly_inside_every_budget(budget_ms):
    """The inner backstop must survive reallocation at every scale.

    A statement timeout at or past its budget is what lets Celery SIGKILL the
    worker before Postgres cancels, orphaning a backend and its xmin (#1479).
    """
    from app.utils.calibration_phase_ledger import _statement_timeout_for

    timeout = _statement_timeout_for(budget_ms)
    assert 1 <= timeout < budget_ms or budget_ms == 1
    assert budget_ms - timeout <= STATEMENT_INNER_MARGIN_MS


def test_the_widened_beat_still_fits_the_celery_soft_limit():
    """Reallocation spends the window; it must never spend the margin."""
    plan = _prod_plan()
    assert plan.by_name(PHASE_FUTURES).statement_timeout_ms < SOFT_LIMIT_MS - CLEANUP_MARGIN_MS
    assert plan.declared_ms + CLEANUP_MARGIN_MS <= SOFT_LIMIT_MS
