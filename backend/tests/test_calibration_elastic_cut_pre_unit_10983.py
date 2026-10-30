"""#10983 — the elastic cut must leave the futures phase room for its roster read.

The accuracy curve froze at 2026-10-30 04:20:29Z. Every beat from 05:39Z on
started fresh (the 04:44Z publish had cleared the checkpoint), ran the futures
roster read (``read:futures_generation``) under a 159,933 ms statement timeout,
and was cancelled at ~162 s — ``QueryCanceledError``, ``consecutive_failures``
climbing, nothing banked.

The 159,933 ms came from :func:`_elastic_cut`. Diagnostics' worst completion had
risen to 718,113 ms, so the inelastic phases claimed 1,202,297 ms of the
1,380,000 ms window and futures was handed the 177,703 ms remainder. The cut's
own guard passed, because 177,703 holds one 138,727 ms unit. But no unit runs
before the roster read, and the last publishing beat had measured that read at
176,654 ms. A failed beat completes no phase, so ``history`` could not move and
the next plan was the same plan: a fixed point.

The specimen below is production's ``calibration:main:phase_ledger`` row read at
2026-10-30 09:25Z (generation 1793349227844). It reproduces the deployed plan to
the millisecond, which is what makes it a specimen rather than an illustration.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks import calibration_main_build as cmb
from app.utils.calibration_phase_ledger import (
    BUDGET_BASIS_ELASTIC_CUT,
    ELASTIC_PHASES,
    ELASTIC_PRE_UNIT_STAGES,
    PHASE_AGGREGATE,
    PHASE_DIAGNOSTICS,
    PHASE_FUTURES,
    PHASE_PUBLISH,
    PHASE_SPORTS,
    PRE_UNIT_MS_KEY,
    derive_plan,
)

PROD_HISTORY: dict[str, list[int]] = {
    PHASE_SPORTS: [27647, 46931, 32965, 35319, 50385, 47931, 68718, 42388, 38598, 37737],
    PHASE_FUTURES: [
        168598, 201025, 210765, 376794, 228605, 237339, 186697, 159355, 203505, 238461,
    ],
    PHASE_AGGREGATE: [545, 676, 290, 823, 830, 695, 1153, 2320, 202, 54],
    PHASE_DIAGNOSTICS: [
        319000, 413153, 409262, 560974, 450573, 517758, 718113, 544796, 490527, 717804,
    ],
    PHASE_PUBLISH: [11277, 7789, 6375, 6411, 6782, 6982, 12380, 7521, 5609, 6805],
}

PROD_FLOORS: dict[str, list[int]] = {
    PHASE_SPORTS: [11526, 15735, 15559, 15699, 19505, 25832, 33463, 14843, 26130, 25663],
    PHASE_FUTURES: [
        88664, 156771, 199190, 127785, 143780, 164819, 162829, 161984, 160939, 162022,
    ],
    PHASE_DIAGNOSTICS: [7, 8, 12, 7, 12, 6, 5, 10, 397979, 138983],
    PHASE_PUBLISH: [
        1144746, 1145285, 993129, 1113249, 939765, 1011339, 1025810, 1161252, 1204322,
        975555,
    ],
}

PROD_UNIT = {"unit_ms": 138727, "units_done": 83, "units_total": 521}

#: The ledger row's own ``stages`` / ``stage_counts`` for the roster read: one
#: read, cancelled at 161,890 ms. A LOWER bound on its cost.
PROD_STAGES = {"read:futures_generation": 161890, "rss:at:read:futures_generation": 186}
PROD_STAGE_COUNTS = {"read:futures_generation": 1}

#: The last PUBLISHING beat's completed roster read (04:20Z run).
COMPLETED_ROSTER_READ_MS = 176654


def _plan(pre_unit_ms=None, unit=PROD_UNIT, history=PROD_HISTORY):
    cost = dict(unit)
    if pre_unit_ms is not None:
        cost[PRE_UNIT_MS_KEY] = pre_unit_ms
    plan = derive_plan(history, floors=PROD_FLOORS, unit_costs={PHASE_FUTURES: cost})
    return {b.name: b for b in plan.budgets}, plan


class TestTheSpecimen:
    def test_without_the_reading_the_deployed_plan_is_reproduced_exactly(self):
        """Pins the diagnosis: this IS the plan production ran at 05:39Z-08:31Z."""
        budgets, _ = _plan()
        futures = budgets[PHASE_FUTURES]
        assert futures.budget_basis == BUDGET_BASIS_ELASTIC_CUT
        assert futures.budget_ms == 177703
        assert futures.statement_timeout_ms == 159933
        # ...and the roster read alone already exceeds it.
        assert futures.statement_timeout_ms < COMPLETED_ROSTER_READ_MS

    def test_with_the_reading_the_cut_is_declined(self):
        budgets, _ = _plan(pre_unit_ms=161890)
        assert budgets[PHASE_FUTURES].budget_basis != BUDGET_BASIS_ELASTIC_CUT

    def test_the_roster_read_fits_the_bound_it_runs_under(self):
        """The anchor: the completed read fits, with a unit's worth to spare."""
        budgets, _ = _plan(pre_unit_ms=161890)
        futures = budgets[PHASE_FUTURES]
        assert futures.statement_timeout_ms > COMPLETED_ROSTER_READ_MS + PROD_UNIT["unit_ms"]

    def test_every_inelastic_phase_still_clears_its_own_worst_completion(self):
        """The fallback must not recreate CAL-P109 on this specimen.

        The proportional squeeze is what the elastic cut was built to avoid,
        because it once put sports under its own measured worst. Here it does
        not: every phase keeps a budget at or above the slowest completion it
        has on record. This is the plan production last published under.
        """
        budgets, _ = _plan(pre_unit_ms=161890)
        for name, observed in PROD_HISTORY.items():
            if name in ELASTIC_PHASES:
                continue
            assert budgets[name].budget_ms >= max(observed), name

    def test_the_declared_total_still_fits_the_window(self):
        _, plan = _plan(pre_unit_ms=161890)
        available = plan.soft_limit_ms - plan.cleanup_margin_ms
        assert sum(b.budget_ms or 0 for b in plan.budgets) <= available


class TestTheGuardOnlyDeclines:
    def test_no_reading_leaves_the_cut_exactly_as_it_was(self):
        with_none, _ = _plan(pre_unit_ms=None)
        without_key, _ = _plan(unit=PROD_UNIT)
        assert with_none == without_key

    def test_a_cheap_roster_read_keeps_the_cut(self):
        """September's roster read (18-26 s) left the cut correct; it must stay."""
        budgets, _ = _plan(pre_unit_ms=25919)
        assert budgets[PHASE_FUTURES].budget_basis == BUDGET_BASIS_ELASTIC_CUT
        assert budgets[PHASE_FUTURES].budget_ms == 177703

    def test_a_read_that_fits_but_leaves_no_unit_declines(self):
        """Room for the read and not for a unit banks nothing either."""
        budgets, _ = _plan(pre_unit_ms=60000)
        assert budgets[PHASE_FUTURES].budget_basis != BUDGET_BASIS_ELASTIC_CUT

    def test_without_a_unit_cost_the_read_alone_is_checked_against_the_timeout(self):
        budgets, _ = _plan(pre_unit_ms=161890, unit={})
        assert budgets[PHASE_FUTURES].budget_basis != BUDGET_BASIS_ELASTIC_CUT
        budgets, _ = _plan(pre_unit_ms=100000, unit={})
        assert budgets[PHASE_FUTURES].budget_basis == BUDGET_BASIS_ELASTIC_CUT

    @pytest.mark.parametrize("junk", [True, False, -5, 0, "161890", None, [1]])
    def test_junk_is_not_a_reading(self, junk):
        cost = dict(PROD_UNIT, **{PRE_UNIT_MS_KEY: junk})
        plan = derive_plan(PROD_HISTORY, floors=PROD_FLOORS, unit_costs={PHASE_FUTURES: cost})
        futures = {b.name: b for b in plan.budgets}[PHASE_FUTURES]
        assert futures.budget_basis == BUDGET_BASIS_ELASTIC_CUT


class TestTheReadingComesFromThePriorBeat:
    def test_the_stage_name_is_the_one_the_frozen_module_records(self):
        import inspect

        from app.tasks import precompute_calibration

        stage = ELASTIC_PRE_UNIT_STAGES[PHASE_FUTURES]
        source = inspect.getsource(precompute_calibration._run_staged_futures)
        assert f'runner.stage("{stage}")' in source

    def test_the_specimen_row_yields_its_cancelled_read(self):
        payload = {"stages": PROD_STAGES, "stage_counts": PROD_STAGE_COUNTS}
        assert cmb._pre_unit_from(payload) == {PHASE_FUTURES: 161890}

    def test_repeated_reads_are_averaged_not_summed(self):
        payload = {
            "stages": {"read:futures_generation": 300000},
            "stage_counts": {"read:futures_generation": 2},
        }
        assert cmb._pre_unit_from(payload) == {PHASE_FUTURES: 150000}

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"stages": PROD_STAGES},
            {"stage_counts": PROD_STAGE_COUNTS},
            {"stages": {"other": 5}, "stage_counts": {"other": 1}},
            {"stages": {"read:futures_generation": 5}, "stage_counts": {"read:futures_generation": 0}},
            {"stages": {"read:futures_generation": True}, "stage_counts": {"read:futures_generation": 1}},
            {"stages": "x", "stage_counts": "y"},
        ],
    )
    def test_a_beat_with_no_usable_reading_yields_nothing(self, payload):
        assert cmb._pre_unit_from(payload) == {}

    def test_the_plan_view_carries_it_and_the_save_view_does_not(self, monkeypatch):
        """Folded for the PLAN; the carry the SAVE folds onto is left untouched."""
        unit_costs = {PHASE_FUTURES: dict(PROD_UNIT)}
        carry = cmb.PhaseCarryover(
            dict(PROD_HISTORY),
            dict(PROD_FLOORS),
            unit_costs,
            {},
            status="ok",
            pre_unit_ms={PHASE_FUTURES: 161890},
        )

        async def _read():
            return carry

        monkeypatch.setattr(cmb, "read_phase_carryover", _read)
        _history, _floors, costs, _ring = asyncio.run(cmb.load_phase_carryover())
        assert costs[PHASE_FUTURES][PRE_UNIT_MS_KEY] == 161890
        assert PRE_UNIT_MS_KEY not in carry.unit_costs[PHASE_FUTURES]
        assert carry.unit_costs is unit_costs

    def test_an_unread_ledger_still_collapses_to_four_empty_dicts(self, monkeypatch):
        async def _read():
            return cmb.PhaseCarryover({}, {}, {}, {}, status="unavailable", unknown=True)

        monkeypatch.setattr(cmb, "read_phase_carryover", _read)
        assert asyncio.run(cmb.load_phase_carryover()) == ({}, {}, {}, {})
