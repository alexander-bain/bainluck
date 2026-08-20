"""CAL-P081 (#2007) — a carried futures phase runs no units, so the rebuild
does not advance on the beats that carry it.

Found while trying to answer Fable's actual question — "is the bank advancing?"
— rather than the code question. The 2026-08-20 20:15Z beat, read live:

    generated_at              2026-08-20T20:17:19Z   (a fresh, successful publish)
    carried                   ['futures', 'sports']
    staged:units_this_beat    0
    staged:rate_reason:no_unit_ran  1
    rebuild_units_banked      13        (unchanged since the 18:22Z beat)
    units_drifted             128 / 128

The publish is correct — CAL-P078's serving bank is what keeps the curve whole
while its successor is built, and ``is_complete`` is satisfied by it. What is
wrong is the SIDE EFFECT: ``compute_calibration_payload`` reuses the carried
phase output and therefore never calls ``_run_staged_futures``, and the unit loop
is the only thing in the system that advances the rebuild. A whole beat of
re-stage is bought for one ~75 s generation read, on a bank that needs about
fifteen more advances.

It compounds with the teardowns in ``test_worker_shutdown_terminal_p081.py``: an
interrupted beat that had already finished futures banks the carry, the next beat
spends itself carrying it, and TWO beats of re-stage are lost per deploy. Six
releases landed between 16:16Z and 20:07Z on 2026-08-20.

The fix is on the WRITE side, not the read side, and deliberately so: the beat
that must not bank a carry is the beat that just ran units and knows it did not
finish. That beat has the evidence; the beat that would consume the carry does
not. It also keeps the change out of the frozen module (ruling 009) — the two
stages it reads, ``staged:units_planned`` and ``staged:units_done``, are already
written by ``_record_convergence_projection`` at the end of every loop.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_main_build import PhaseRunner
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)


def _runner(stages: dict[str, int]) -> PhaseRunner:
    plan = PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=None,
                statement_timeout_ms=None,
                measured_input=True,
            ),
        ),
    )
    ledger = PhaseLedger(
        plan=plan,
        population_version="q268",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
        phases=(PHASE_FUTURES,),
    )
    ledger.stages.update(stages)
    runner = PhaseRunner.__new__(PhaseRunner)
    runner.ledger = ledger
    return runner


class TestRebuildInFlight:
    def test_the_live_specimen_reads_in_flight(self):
        """13 of 128, which is where the bank actually sat."""
        assert _runner({"staged:units_planned": 128, "staged:units_done": 13}) \
            .rebuild_in_flight() is True

    def test_a_finished_rebuild_is_not_in_flight(self):
        assert _runner({"staged:units_planned": 128, "staged:units_done": 128}) \
            .rebuild_in_flight() is False

    def test_a_beat_whose_loop_never_ran_cannot_answer_and_says_no(self):
        """The asymmetry, on purpose. A carried beat has no stages from the loop,
        so it does not know — and the beat that must act on the answer is the one
        that DID run units. Guessing ``True`` here would suppress the carry
        forever on evidence nobody gathered."""
        assert _runner({}).rebuild_in_flight() is False

    @pytest.mark.parametrize("stages", [
        {"staged:units_planned": 0, "staged:units_done": 0},
        {"staged:units_planned": 128},
        {"staged:units_done": 13},
        {"staged:units_planned": "128", "staged:units_done": 13},
    ])
    def test_incomplete_or_malformed_evidence_never_fabricates_a_verdict(self, stages):
        assert _runner(stages).rebuild_in_flight() is False


class TestTheFuturesCarryIsWithheld:
    """``build_checkpoint``'s behaviour, driven through the real method."""

    @staticmethod
    def _prepared(stages, *, futures_done=True):
        from app.tasks.calibration_main_build import (
            DONE_STATUSES,
            new_main_checkpoint,
        )

        runner = _runner(stages)
        runner.population_version = "q268"
        runner.fingerprint = "fp"
        runner.owner = "test:1"
        runner.generation = 1
        runner.carried_phases = set()
        runner._captured = {}
        runner.checkpoint = new_main_checkpoint(
            version="q268", fingerprint="fp", owner="test:1", generation=1
        )
        if futures_done:
            runner.ledger.records[PHASE_FUTURES].status = sorted(DONE_STATUSES)[0]
            runner._captured[PHASE_FUTURES] = {}
        return runner

    def test_an_in_flight_rebuild_withholds_the_futures_carry_by_name(self):
        runner = self._prepared(
            {"staged:units_planned": 128, "staged:units_done": 13}
        )
        _, outcomes = runner.build_checkpoint()
        assert outcomes.get(PHASE_FUTURES) == "rebuild_in_flight"

    def test_a_finished_rebuild_does_not_withhold_it(self):
        """The control. A guard that always withholds is not a guard, it is a
        deletion of the carry — and the carry is correct once the rebuild has no
        units outstanding."""
        runner = self._prepared(
            {"staged:units_planned": 128, "staged:units_done": 128}
        )
        _, outcomes = runner.build_checkpoint()
        assert outcomes.get(PHASE_FUTURES) != "rebuild_in_flight"

    def test_a_beat_with_no_loop_evidence_behaves_exactly_as_before(self):
        runner = self._prepared({})
        _, outcomes = runner.build_checkpoint()
        assert outcomes.get(PHASE_FUTURES) != "rebuild_in_flight"
