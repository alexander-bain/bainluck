"""CAL-P071 — the ETA divides by the phase's own budget, not the whole beat.

`PhasePlan.unit_projection` used `max_phase_ms` — the statement timeout a phase
gets **when it is handed the entire window**. That is the right ceiling for the
feasibility question ("could this phase ever fit?") and the wrong divisor for the
throughput question ("how many units will this beat finish?").

Production, 2026-08-18, the first q268 build:

    unit_ms       126,958      budget_ms (futures)    177,374
    max_phase_ms  1,350,000    units_remaining        125

    reported:  units_per_beat 10   beats_remaining 13
    truth:     units_per_beat  1   beats_remaining 125

Thirteen hourly beats reads as "tonight". A hundred and twenty-five reads as
five days, against a hard deadline 52 hours out — the published q267 artifact
ages out of SERVE_MAX_AGE_S at 2026-08-21T00:16Z, after which /api/calibration
has nothing servable at any tier.

The second half is worse than the factor of ten. Three consecutive beats banked
**2, then 1, then 0** units while the estimate sat at 13 the whole time, because
observed throughput is not an input to it. An ETA that cannot fall as the build
slows is not an estimate.
"""

import math

import pytest

from app.utils.calibration_phase_ledger import (
    BUDGET_SAFETY,
    PHASE_FUTURES,
    derive_plan,
)

# The production numbers above, so a reader can check the arithmetic against the
# ledger row they came from rather than against a fixture nobody can locate.
PROD_UNIT_MS = 126_958
PROD_PHASE_BUDGET_MS = 177_374
PROD_UNITS_TOTAL = 128
PROD_UNITS_DONE = 3
WHOLE_BEAT_CEILING_MS = 1_350_000


def _plan_with_budget(budget_ms: int | None):
    """A plan whose futures phase carries a measured cost and, optionally, a
    declared budget of exactly ``budget_ms``.

    A budget is ``max(observed) * BUDGET_SAFETY``, so the observations are
    divided by the safety factor to land on the target. Feeding the target in
    raw produces a budget 1.5x too generous — which is how the first cut of
    this test asserted 63 beats against production's 125 and looked like a
    disagreement with the fix rather than with the fixture.
    """
    history = (
        {PHASE_FUTURES: [int(budget_ms / BUDGET_SAFETY)] * 10} if budget_ms else {}
    )
    return derive_plan(
        history,
        unit_costs={
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": PROD_UNITS_TOTAL,
                "units_done": PROD_UNITS_DONE,
            }
        },
    )


def test_a_phase_with_a_declared_budget_is_projected_against_that_budget():
    plan = _plan_with_budget(PROD_PHASE_BUDGET_MS)
    budget = plan.by_name(PHASE_FUTURES)
    assert budget.budget_ms, "fixture must actually earn a budget or it proves nothing"

    proj = plan.unit_projection(PHASE_FUTURES)
    assert proj["per_beat_basis"] == "phase_budget"
    assert proj["per_beat_ms"] == budget.budget_ms
    assert proj["units_per_beat"] == budget.budget_ms // PROD_UNIT_MS
    assert proj["beats_remaining"] == math.ceil(
        proj["units_remaining"] / proj["units_per_beat"]
    )


def test_the_production_row_now_reports_125_beats_and_not_13():
    """The 2026-08-18 specimen, pinned to its real numbers."""
    plan = _plan_with_budget(PROD_PHASE_BUDGET_MS)
    assert plan.by_name(PHASE_FUTURES).budget_ms == PROD_PHASE_BUDGET_MS

    proj = plan.unit_projection(PHASE_FUTURES)
    assert proj["units_remaining"] == 125
    assert proj["units_per_beat"] == 1
    assert proj["beats_remaining"] == 125

    # What the same row used to say, computed the old way, so the regression
    # this test guards is legible without a git blame.
    whole_beat_answer = WHOLE_BEAT_CEILING_MS // PROD_UNIT_MS
    assert whole_beat_answer == 10
    assert math.ceil(125 / whole_beat_answer) == 13


def test_a_phase_with_no_declared_budget_falls_back_and_says_so():
    """No budget is a real state (a provisional plan has none), and the ceiling
    is the honest divisor for it. What must never happen is the fallback being
    indistinguishable from a phase measured against its own allotment."""
    plan = _plan_with_budget(None)
    assert plan.by_name(PHASE_FUTURES).budget_ms is None

    proj = plan.unit_projection(PHASE_FUTURES)
    assert proj["per_beat_basis"] == "whole_beat_ceiling"
    assert proj["per_beat_ms"] == plan.max_phase_ms
    assert proj["units_per_beat"] == plan.max_phase_ms // PROD_UNIT_MS


def test_a_budget_too_small_for_one_unit_reports_minus_one_not_a_big_number():
    """The `-1` convention survives the divisor change, and now REACHES cases it
    could not before: a phase can be allotted less than one unit's cost while a
    whole beat would comfortably hold it. Under the old divisor that state was
    unreportable — it rendered as a cheerful small integer."""
    plan = derive_plan(
        {PHASE_FUTURES: [PROD_UNIT_MS // 4] * 10},
        unit_costs={
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": PROD_UNITS_TOTAL,
                "units_done": PROD_UNITS_DONE,
            }
        },
    )
    budget = plan.by_name(PHASE_FUTURES)
    assert budget.budget_ms < PROD_UNIT_MS
    # ...and a whole beat WOULD hold several, which is what made this invisible
    assert plan.max_phase_ms // PROD_UNIT_MS >= 1

    proj = plan.unit_projection(PHASE_FUTURES)
    assert proj["units_per_beat"] == 0
    assert proj["beats_remaining"] == -1


def test_the_payload_carries_the_basis_so_a_reader_cannot_guess_wrong():
    plan = _plan_with_budget(PROD_PHASE_BUDGET_MS)
    detail = plan.as_payload()["feasibility"]["units"][PHASE_FUTURES]
    assert detail["per_beat_basis"] == "phase_budget"
    assert detail["per_beat_ms"] == plan.by_name(PHASE_FUTURES).budget_ms


@pytest.mark.parametrize("units_done", [0, None])
def test_a_phase_that_has_completed_nothing_projects_nothing(units_done):
    """Unchanged, and load-bearing: zero completed units means there is no
    measured cost, and inventing a rate from a cancelled phase is the exact
    false-comfort this projection already suffers from elsewhere."""
    plan = derive_plan(
        {PHASE_FUTURES: [PROD_PHASE_BUDGET_MS] * 10},
        unit_costs={
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": PROD_UNITS_TOTAL,
                "units_done": units_done,
            }
        },
    )
    assert plan.unit_projection(PHASE_FUTURES) is None
