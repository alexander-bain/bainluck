"""CAL-P109 (#2045) — the window's overrun is charged to the phase that can pay it.

The producer was not stalled. It was FLAPPING: of the 164 beats in
``calibration:beat_gauge_history`` on 2026-08-28, 77 completed, 61 failed and 26
were cancelled — a 47% loss rate, and two consecutive losses is exactly what
``calibration_publish_age`` pages on. It fired on 2026-08-25, -26 and -27.

The mechanism, read off production's own ledger (generation 1787924136928):

``derive_plan`` budgets each phase at ``max(observed) * BUDGET_SAFETY`` and, when
the declared total overruns the window, scales EVERY phase by the same factor.
``futures`` alone declares more than the whole window (~1.95M ms of 1.38M), so
the factor landed at ~0.617 — and the four phases that did not cause the overrun
were each cut to ~62% of their own worst measured completion. ``sports`` was
handed a 3,391 ms budget and a 3,052 ms statement timeout while its ``read:events``
query had completed as slowly as 3,661 ms; its floor ring — the durations at
which it was CANCELLED — was ten entries deep at 3,137-4,180 ms.

The cost of that cut is not proportional, because the phases are not alike.
``futures`` runs a unit loop that asks ``_unit_fits_in_window`` before each unit
and stops between them with everything it proved banked; a shorter budget costs
it UNITS. Every other phase is one statement or a fixed sequence of them, with
no partial credit: a budget under its cost is a cancelled beat that publishes
nothing — throwing away a futures phase that had already completed, over about
one second of sports.

So the overrun goes to the elastic phase and the inelastic phases keep their
measured budgets. The anchor assertion is
:meth:`TestTheIncident.test_sports_statement_timeout_clears_every_recorded_failure`:
the bound sports runs under must exceed every duration at which sports has been
observed to fail. Under the proportional squeeze it did not, and the beat died.
"""

from __future__ import annotations

import pytest

from app.utils.calibration_phase_ledger import (
    BUDGET_BASIS_ELASTIC_CUT,
    BUDGET_BASIS_MEASURED,
    BUDGET_BASIS_SCALED_DOWN,
    BUDGET_BASIS_UNMEASURED,
    ELASTIC_PHASES,
    PHASE_AGGREGATE,
    PHASE_DIAGNOSTICS,
    PHASE_FUTURES,
    PHASE_PUBLISH,
    PHASE_SPORTS,
    REQUIRED_PHASES,
    derive_plan,
)

# --------------------------------------------------------------------------
# Production, 2026-08-28. ``history`` is the ledger's own rolling window with
# the publishing beat's contribution removed, because the plan was derived
# BEFORE that beat folded its durations in. Each inelastic phase's UNSCALED
# budget (``ceil(max * 1.5)``) reproduces the deployed plan exactly once
# multiplied by the deployed scale of 0.61744 — 5,492 -> 3,391; 282,602 ->
# 174,535; 141 -> 87; 861 -> 531. That is what makes these a specimen rather
# than an illustration.
#
# The scale itself cannot be re-derived from these lists alone: the futures
# observation that set it (~1,297,000 ms) has already aged out of the 10-slot
# window, so a replay computes 0.650. Every assertion below is therefore written
# on the kinder reconstructed scale, which is the generous case for the old code.
# --------------------------------------------------------------------------
PROD_HISTORY: dict[str, list[int]] = {
    PHASE_FUTURES: [
        1138827, 317911, 1113937, 1223020, 1116814, 1157598, 1147797, 1019422, 1107829,
    ],
    PHASE_SPORTS: [1914, 2351, 2914, 1142, 1522, 3378, 3661, 1907, 3283],
    PHASE_DIAGNOSTICS: [
        188401, 102706, 82719, 97927, 86769, 91046, 134300, 120394, 116090,
    ],
    PHASE_AGGREGATE: [76, 63, 94, 54, 58, 57, 53, 55, 54],
    PHASE_PUBLISH: [574, 197, 195, 426, 213, 223, 395, 269, 431],
}

#: Durations at which each phase was CANCELLED — a lower bound on its true cost,
#: never a budget (the module is emphatic about that, and right).
PROD_FLOORS: dict[str, list[int]] = {
    PHASE_SPORTS: [3893, 3809, 4180, 3792, 3223, 3168, 3189, 3137, 3190, 3144],
    PHASE_FUTURES: [
        1293413, 1149793, 1340886, 1105801, 1142055, 1057299, 1244711, 915519, 779025,
        285176,
    ],
    PHASE_DIAGNOSTICS: [
        50673, 35884, 45669, 73197, 116002, 58922, 97215, 49246, 4512, 92590,
    ],
    PHASE_PUBLISH: [2037, 1817, 2007, 1910, 3732, 2508, 2179, 2350, 2663, 2207],
}

PROD_UNIT_COSTS = {PHASE_FUTURES: {"unit_ms": 153380, "units_done": 85, "units_total": 128}}


def _plan(**overrides):
    kwargs: dict = {
        "floors": PROD_FLOORS,
        "unit_costs": PROD_UNIT_COSTS,
    }
    kwargs.update(overrides)
    history = kwargs.pop("history", PROD_HISTORY)
    return derive_plan(history, **kwargs)


def _by_name(plan) -> dict:
    return {b.name: b for b in plan.budgets}


class TestTheIncident:
    """The specimen: production's own numbers, on the day the watchdog fired."""

    def test_sports_statement_timeout_clears_every_recorded_failure(self):
        """The regression, stated as the fact that was false in production.

        A phase must not be bounded below a duration at which it has already
        been observed to die. Sports' floor ring says it was cancelled ten times
        between 3,137 ms and 4,180 ms; the deployed plan ran it under a 3,052 ms
        statement timeout, so an ordinary-slow beat was a coin flip.

        Asserted against the STATEMENT TIMEOUT rather than the budget because
        the timeout is the bound Postgres actually enforces — it is what
        cancelled ``read:events`` and killed the beat. ``budget_ms`` is a plan;
        exceeding it is survivable (production's ``aggregate`` ran 1,111 ms
        against an 87 ms budget and completed).
        """
        sports = _by_name(_plan())[PHASE_SPORTS]
        worst_failure = max(PROD_FLOORS[PHASE_SPORTS])
        assert sports.statement_timeout_ms > worst_failure, (
            f"sports bounded at {sports.statement_timeout_ms} ms, but it has been "
            f"cancelled at {worst_failure} ms"
        )

    def test_every_inelastic_phase_keeps_its_full_measured_budget(self):
        """Nothing that cannot do partial work is asked to absorb the overrun."""
        plan = _by_name(_plan())
        for name in REQUIRED_PHASES:
            if name in ELASTIC_PHASES:
                continue
            expected = -(-max(PROD_HISTORY[name]) * 3 // 2)  # ceil(max * 1.5)
            assert plan[name].budget_ms == expected, name
            assert plan[name].budget_basis == BUDGET_BASIS_MEASURED, name

    def test_only_the_elastic_phase_is_budgeted_under_its_own_worst_completion(self):
        """The whole defect in one line, and the whole fix in the same line.

        Under the proportional squeeze, ALL FIVE phases were budgeted below
        their own slowest successful run — futures 1,192,139 vs 1,223,020;
        sports 3,568 vs 3,661; diagnostics 183,643 vs 188,401; aggregate 91 vs
        94; publish 559 vs 574. Every phase was planned to fail on a repeat of
        its own worst good day.

        Afterwards exactly one still is, and it is the one that answers a cut by
        doing less work. Note this rescues ``diagnostics`` too, which was 4,758 ms
        short of its own worst completion and is not otherwise part of this story.
        """
        plan = _by_name(_plan())
        under = {
            b.name
            for b in plan.values()
            if b.budget_ms is not None and b.budget_ms < max(PROD_HISTORY[b.name])
        }
        assert under == set(ELASTIC_PHASES), under

    def test_the_elastic_phase_absorbs_the_whole_overrun_and_says_so(self):
        plan = _by_name(_plan())
        futures = plan[PHASE_FUTURES]
        assert futures.budget_basis == BUDGET_BASIS_ELASTIC_CUT
        # It is CUT, never widened: an elastic cut may only ever take away.
        assert futures.budget_ms < -(-max(PROD_HISTORY[PHASE_FUTURES]) * 3 // 2)

    def test_the_declared_total_still_fits_the_window(self):
        """Reallocation, not creation — the ceiling is the same as before."""
        plan = _plan()
        available = plan.soft_limit_ms - plan.cleanup_margin_ms
        assert sum(b.budget_ms or 0 for b in plan.budgets) <= available

    def test_the_elastic_phase_can_still_bank_at_least_one_unit(self):
        """A cut past one unit is not "less work", it is no work.

        The futures loop banks per unit; a budget that cannot hold a whole one
        buys nothing and the beat resumes from the same cursor forever. That is
        the fatal shape this change moves OFF the inelastic phases, so it must
        not be created on the elastic one.
        """
        futures = _by_name(_plan())[PHASE_FUTURES]
        assert futures.budget_ms >= PROD_UNIT_COSTS[PHASE_FUTURES]["unit_ms"]

    def test_the_proportional_squeeze_is_what_put_sports_under_its_own_floor(self):
        """Guards the DIAGNOSIS, so a future reader can re-derive it.

        Worked from the same inputs, in the same arithmetic the old code used:
        every phase scaled by ``available / declared``. It reproduces the
        deployed plan's sports budget of 3,391 ms and its 3,052 ms statement
        timeout — under every one of the ten durations at which sports has been
        cancelled. If this stops holding, the incident's explanation has changed
        and the rest of this file needs re-reading.
        """
        from app.utils.calibration_phase_ledger import (
            BUDGET_SAFETY,
            CLEANUP_MARGIN_MS,
            SOFT_LIMIT_MS,
            _statement_timeout_for,
        )

        declared = {
            name: -(-max(obs) * 3 // 2) for name, obs in PROD_HISTORY.items()
        }
        assert BUDGET_SAFETY == 1.5, "the ceil(max * 3 // 2) shorthand above"
        available = SOFT_LIMIT_MS - CLEANUP_MARGIN_MS
        scale = available / sum(declared.values())

        # Deliberately NOT asserted equal to the deployed 3,391 ms. The
        # reconstruction reaches 3,568 ms because the futures observation that
        # set production's scale (~1,297,000 ms) has since aged out of the
        # 10-slot window, making the declared total here smaller and the scale
        # correspondingly kinder (0.650 vs the deployed 0.617). The DIRECTION is
        # what the diagnosis rests on, and the reconstruction is the generous
        # case: even at the kinder scale, sports lands under its floor ring.
        squeezed_sports = int(declared[PHASE_SPORTS] * scale)
        squeezed_bound = _statement_timeout_for(squeezed_sports)
        assert squeezed_bound < max(PROD_FLOORS[PHASE_SPORTS]), (
            "the squeeze must bound sports below durations at which it has "
            "already been cancelled — that is the incident"
        )
        # Not a marginal overlap: even at the kinder reconstructed scale, most
        # of the recorded cancellations sit ABOVE the bound the plan would set,
        # so an ordinary-slow beat is a coin flip rather than an outlier. At the
        # deployed 0.61744 the bound was 3,052 ms — below all ten.
        doomed = [f for f in PROD_FLOORS[PHASE_SPORTS] if f > squeezed_bound]
        assert len(doomed) >= 5, doomed  # half the ring, at the kinder scale
        # And the four inelastic phases' UNSCALED budgets are exact against
        # production: each deployed budget is this number times the deployed
        # 0.61744. That is what makes these inputs a specimen.
        assert declared[PHASE_SPORTS] == 5492
        assert declared[PHASE_DIAGNOSTICS] == 282602
        assert declared[PHASE_AGGREGATE] == 141
        assert declared[PHASE_PUBLISH] == 861


class TestItRefusesWhenItCannotBeSure:
    """Every ambiguous case falls back to the old proportional path.

    The elastic cut is an optimisation over a squeeze that at least always
    produced a plan. It must never be the reason a plan cannot be produced.
    """

    def test_an_unmeasured_phase_leaves_the_plan_provisional_and_uncut(self):
        history = {k: v for k, v in PROD_HISTORY.items() if k != PHASE_SPORTS}
        plan = _by_name(_plan(history=history))
        assert plan[PHASE_SPORTS].budget_basis == BUDGET_BASIS_UNMEASURED
        assert plan[PHASE_FUTURES].budget_basis != BUDGET_BASIS_ELASTIC_CUT

    def test_a_plan_with_no_elastic_phase_at_all_falls_back_to_the_squeeze(self):
        """Nothing in the plan can absorb a cut, so everyone shares it again."""
        inelastic = tuple(n for n in REQUIRED_PHASES if n not in ELASTIC_PHASES)
        history = {n: [800_000] for n in inelastic}
        plan = _by_name(_plan(history=history, phases=inelastic, floors={}, unit_costs={}))
        assert plan[PHASE_SPORTS].budget_basis == BUDGET_BASIS_SCALED_DOWN

    def test_a_remainder_below_one_unit_falls_back_to_the_squeeze(self):
        """A cut past one whole unit banks nothing, so it is not taken.

        Asserted on SPORTS: the question is whether the inelastic phases got the
        protection, and the fallback is precisely them losing it again.
        """
        history = dict(PROD_HISTORY)
        history[PHASE_DIAGNOSTICS] = [900_000]
        plan = _by_name(_plan(history=history))
        assert plan[PHASE_SPORTS].budget_basis == BUDGET_BASIS_SCALED_DOWN

    def test_inelastic_phases_that_alone_overrun_fall_back_to_the_squeeze(self):
        """The elastic phase cannot pay a shortfall bigger than itself."""
        history = dict(PROD_HISTORY)
        history[PHASE_DIAGNOSTICS] = [2_000_000]
        plan = _by_name(_plan(history=history))
        assert plan[PHASE_SPORTS].budget_basis == BUDGET_BASIS_SCALED_DOWN

    def test_a_window_that_was_never_over_declared_is_untouched(self):
        """No overrun, no cut — and nothing is scaled UP to fill the window."""
        history = {name: [1000] for name in REQUIRED_PHASES}
        plan = _by_name(_plan(history=history, floors={}, unit_costs={PHASE_FUTURES: {"unit_ms": 100}}))
        for name in REQUIRED_PHASES:
            assert plan[name].budget_ms == 1500, name
            assert plan[name].budget_basis != BUDGET_BASIS_ELASTIC_CUT, name


class TestTheDeclarationItself:
    def test_futures_is_the_only_elastic_phase(self):
        """Elasticity is a property of the CODE — the unit loop with a resumable
        cursor — not a preference. Adding a name here without giving that phase
        partial credit would hand it a cut it cannot survive."""
        assert ELASTIC_PHASES == frozenset({PHASE_FUTURES})

    @pytest.mark.parametrize("name", sorted(ELASTIC_PHASES))
    def test_every_elastic_phase_is_required_and_resumable(self, name):
        from app.utils.calibration_phase_ledger import RESUMABLE_PHASES

        assert name in REQUIRED_PHASES
        assert name in RESUMABLE_PHASES


class TestTheFailureLogNamesTheRightPhase:
    """CAL-P109 (#2045) — ``failed_phase`` vs ``completed_required``.

    The build's failure log printed ``completed_required`` under the label
    "phase group". A beat that got through futures and was then cancelled in
    sports logged ``phase group ['futures']`` — accusing, by name, the one phase
    that had worked. The cancelled statement was sports' ``read:events``.
    """

    @staticmethod
    def _ledger():
        from app.utils.calibration_phase_ledger import PhaseLedger, derive_plan as _dp

        return PhaseLedger(
            plan=_dp({}),
            population_version="v1",
            owner="test",
            generation=1,
            input_fingerprint="fp",
        )

    def test_the_phase_that_died_is_not_the_phase_that_finished(self):
        ledger = self._ledger()
        ledger.begin(PHASE_FUTURES, now_ms=0)
        ledger.complete(PHASE_FUTURES, now_ms=1_100_000)
        ledger.begin(PHASE_SPORTS, now_ms=1_100_000)
        ledger.close_open_phase(now_ms=1_103_500, status="timeout", detail="read:events")

        assert ledger.completed_required == (PHASE_FUTURES,)
        assert ledger.failed_phase == PHASE_SPORTS

    def test_no_phase_in_a_floor_status_names_nobody(self):
        """A run that died between phases has no failing phase, and guessing the
        nearest one is how the original line came to be wrong."""
        ledger = self._ledger()
        ledger.begin(PHASE_FUTURES, now_ms=0)
        ledger.complete(PHASE_FUTURES, now_ms=10)
        ledger.close_open_phase(now_ms=20, status="timeout")

        assert ledger.failed_phase is None
