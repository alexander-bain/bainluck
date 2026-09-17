"""CAL-P1300 (#6275): the unit fence pinned the build, and nothing could reopen it.

THE SPECIMEN, read off production's own ledger across TWO consecutive beats
(``calibration:main:phase_ledger``, 2026-09-15 12:32:16Z and 13:32Z), after
``36a29c945`` reached ``bainluck-heavy`` at 11:48:44Z::

    staged:units_this_beat                  2          2
    staged:units_completed_this_beat        0          0
    staged:units_cancelled                  2          2
    staged:unit_cancelled_after_ms    483,862    484,266
    staged:unit_bound_ms:futures      483,000    483,000
    staged:unit_bound_headroom_ms     347,841    347,841
    staged:units_banked                52/128     52/128   <- pinned
    checkpoint_advanced                 false      false
    cancelled unit hashes    10dcfe0e003106f1, b67e4028d14c2aab  (THE SAME TWO)

The same two units, retried an hour apart against the same fence, cost the same
and died the same way. That is not a slow re-stage — it is a closed door.

WHY IT CANNOT REOPEN. The fence is built by ``statement_timeout_for_unit`` from
measurements over COMPLETED units only::

    mean_basis  = 128,250 * STAGED_UNIT_OVERRUN_FACTOR (4.0) = 513,000
    worst_basis = 268,898 * BUDGET_SAFETY              (1.5) = 403,347
    basis       = max(...)             = 513,000
    fence       = 513,000 - 30,000     = 483,000      <- reproduced exactly

Its safety property is deliberate and documented: "it cannot run away, because
widening requires a COMPLETION at the wider size". #6275 raised the true cost of
a unit above the fence, so no unit can complete, so no completion can enter
either reference, so the fence can never widen. Every later beat reproduces the
arithmetic exactly, for as many beats as the build has left.

WHY THE EXISTING GUARD DOES NOT CATCH IT. ``_level_self_blocked`` (CAL-P1027)
withdraws a self-sustaining level only when ZERO units ran AND
``window_stop:unit_too_large`` fired — the fence refusing to START a unit. Here
the fence ADMITS units and then kills them, so the first condition is false and
the stale level is carried forward untouched. Same disease, adjacent case, no
coverage. CAL-P167 (#1978) is the same ratchet at a third entry point.

THE REPAIR, in ``calibration_main_build`` (``precompute_calibration.py`` is
frozen under ruling 009 and is not touched):

* ``_level_refuted_by_cancellation`` — units ran, none completed, and the fence
  that killed them was the LEVEL'S rather than the window's (positive headroom).
* the carry then withdraws BOTH references, because the fence is
  ``max(mean_basis, worst_basis)`` and dropping only the mean would hand the
  next beat 403,347 ms — TIGHTER than the bound just proven too small.
* with neither measured, the fence's own documented no-measurement path applies:
  the unit gets the PHASE bound. One honest attempt per beat, still inner to the
  beat's deadline, which is the widest thing ever on offer.

Revert any part and the beats below reproduce production exactly: two units
admitted, zero banked, forever, on numbers that never move.
"""

from __future__ import annotations

from app.tasks import calibration_main_build as cmb
from app.utils.calibration_phase_ledger import (
    BUDGET_SAFETY,
    PHASE_FUTURES,
    STAGED_UNIT_OVERRUN_FACTOR,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)

# -- The production numbers. Nothing below invents one. ------------------------
PROD_UNIT_MS = 128_250          # staged:prior_unit_ms
PROD_UNIT_WORST_MS = 268_898    # staged:unit_worst_carried_ms:futures
PROD_FENCE_MS = 483_000         # staged:unit_bound_ms:futures
PROD_HEADROOM_MS = 347_841      # staged:unit_bound_headroom_ms:futures
PROD_CANCELLED_MS = 483_862     # staged:unit_cancelled_after_ms, first beat
PROD_BANKED = 52
PROD_UNITS_TOTAL = 128
PROD_PHASE_BUDGET_MS = 1_283_478
PROD_PHASE_TIMEOUT_MS = 1_253_478


def _plan(*, unit_ms: int | None, unit_ms_worst: int | None, units_done: int) -> PhasePlan:
    return PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=PROD_PHASE_BUDGET_MS,
                statement_timeout_ms=PROD_PHASE_TIMEOUT_MS,
                measured_input=True,
                observations=10,
                unit_ms=unit_ms,
                unit_ms_worst=unit_ms_worst,
                units_total=PROD_UNITS_TOTAL,
                units_done=units_done,
            ),
        ),
        soft_limit_ms=1_500_000,
        cleanup_margin_ms=120_000,
    )


def _ledger_for(plan: PhasePlan) -> PhaseLedger:
    return PhaseLedger(
        plan=plan,
        population_version="q271",
        owner="test:1",
        generation=1,
        input_fingerprint="80a180b082f22181a326dfcfb20429b2",
    )


def _runner(
    *,
    completed: tuple[int, ...] = (),
    cancelled: tuple[int, ...] = (),
    headroom_ms: int | None = PROD_HEADROOM_MS,
    bound_ms: int | None = PROD_FENCE_MS,
    banked: int = PROD_BANKED,
    record_cancel_counter: bool = True,
) -> cmb.PhaseRunner:
    """A runner in the state one beat leaves behind.

    ``staged:units_cancelled`` is written the way production writes it — by the
    cancel path in ``precompute_calibration`` — rather than derived from the
    stage tally, because the predicate under test reads that counter and a fake
    that derived it could never see the two disagree.

    **#6599: the BOUND is recorded beside the headroom, because the fence writes
    them as a pair and the predicate now reads them as one.** This rig recorded
    only the headroom, which left its beats unable to say how much window the
    fence had to work with — and "347,841 ms of headroom" means opposite things
    against a 483,000 ms bound (the LEVEL bit, this specimen) and against a
    350,000 ms one (the window bit). Both values here are production's own, off
    the 12:32:16Z row, so the beats below describe the beat they always claimed
    to. See ``test_calibration_window_bound_is_not_a_level_refutation_6599.py``
    for the latch that made the missing half matter.
    """
    runner = cmb.PhaseRunner(
        plan=_plan(
            unit_ms=PROD_UNIT_MS, unit_ms_worst=PROD_UNIT_WORST_MS, units_done=PROD_BANKED
        ),
        checkpoint=cmb.new_main_checkpoint(
            version="q271", fingerprint="fp", owner="test:1", generation=1
        ),
        checkpoint_action="fresh",
        owner="test:1",
        generation=1,
        fingerprint="fp",
        population_version="q271",
    )
    for ms in completed:
        runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, ms, completed=True)
    for ms in cancelled:
        runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, ms, completed=False)
        if record_cancel_counter:
            runner.ledger.record_stage("staged:units_cancelled", 1)
    if headroom_ms is not None:
        runner.ledger.record_gauge(
            f"staged:unit_bound_headroom_ms:{PHASE_FUTURES}", headroom_ms
        )
    if bound_ms is not None:
        runner.ledger.record_gauge(f"staged:unit_bound_ms:{PHASE_FUTURES}", bound_ms)
    runner.ledger.record_gauge("staged:units_banked", banked)
    return runner


def _production_beat() -> cmb.PhaseRunner:
    """The 12:32:16Z beat: two units admitted, both cancelled at the fence."""
    return _runner(cancelled=(PROD_CANCELLED_MS, 483_228))


# =============================================================================
# 1. THE LATCH — reproduce the fence, then show nothing can widen it
# =============================================================================


class TestTheLatch:
    def test_the_production_fence_is_reproduced_from_the_carried_level(self):
        """The premise, replayed through the real predicate: production's two
        carried references produce production's 483,000 ms fence exactly. If
        this drifts, every number in this file is describing something else."""
        ledger = _ledger_for(
            _plan(
                unit_ms=PROD_UNIT_MS,
                unit_ms_worst=PROD_UNIT_WORST_MS,
                units_done=PROD_BANKED,
            )
        )
        assert ledger.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0) == PROD_FENCE_MS

    def test_the_mean_is_what_sets_it_and_the_worst_is_not_enough_to_widen(self):
        """Which reference dominates decides what a repair has to withdraw.
        Dropping only the mean leaves 1.5 * worst — TIGHTER than the bound that
        just failed, so a half repair makes the pin worse, not better."""
        mean_basis = int(PROD_UNIT_MS * STAGED_UNIT_OVERRUN_FACTOR)
        worst_basis = int(PROD_UNIT_WORST_MS * BUDGET_SAFETY)
        assert mean_basis > worst_basis
        mean_only_withdrawn = _ledger_for(
            _plan(unit_ms=None, unit_ms_worst=PROD_UNIT_WORST_MS, units_done=PROD_BANKED)
        ).statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
        assert mean_only_withdrawn < PROD_FENCE_MS

    def test_a_cancelled_unit_teaches_the_fence_nothing(self):
        """The lock itself. A beat whose every unit was cancelled reports no
        completed cost and no completed worst, so neither reference can move —
        which is why the next beat re-derives the identical fence."""
        beat = _production_beat()
        assert beat.ledger.stage_counts[cmb.STAGED_UNIT_STAGE] == 2
        assert beat.ledger.stage_completed_mean_ms(cmb.STAGED_UNIT_STAGE) is None
        assert beat.ledger.stage_completed_max_ms(cmb.STAGED_UNIT_STAGE) is None
        assert cmb._unit_costs_from(beat) == {}

    def test_the_existing_guard_does_not_cover_it(self):
        """CAL-P1027's withdrawal needs ZERO units run; here two ran. This is
        the gap, and it is the whole reason the new predicate exists."""
        assert cmb._level_self_blocked(_production_beat()) is False


# =============================================================================
# 2. THE PREDICATE — three conditions, and what each one refuses
# =============================================================================


class TestTheRefutationPredicate:
    def test_it_fires_on_the_production_beat(self):
        assert cmb._level_refuted_by_cancellation(_production_beat()) is True

    def test_one_completion_keeps_the_level(self):
        """A completion is a live measurement. However many siblings were
        cancelled beside it, the level still describes something real and the
        ordinary CAL-P163 path must keep it."""
        beat = _runner(completed=(120_000,), cancelled=(PROD_CANCELLED_MS,))
        assert cmb._level_refuted_by_cancellation(beat) is False

    def test_a_beat_that_ran_no_unit_is_not_a_refutation(self):
        """That state belongs to ``_level_self_blocked``, which reads a
        different pair of stages. Claiming it here would withdraw a level on a
        beat that never tested it."""
        beat = _runner(cancelled=())
        assert cmb._level_refuted_by_cancellation(beat) is False

    def test_a_window_bound_cancellation_is_not_a_refutation(self):
        """THE ONE THAT KEEPS THIS HONEST. A unit killed because the beat ran
        out of time says nothing about what a unit intrinsically costs. Zero
        headroom is exactly that case, and withdrawing on it would throw away a
        good measurement every time a beat ended busy."""
        beat = _runner(cancelled=(PROD_CANCELLED_MS, 483_228), headroom_ms=0)
        assert cmb._level_refuted_by_cancellation(beat) is False

    def test_an_unrecorded_headroom_is_not_a_refutation(self):
        """Absent evidence is not evidence (ruling 075): with no headroom gauge
        we cannot tell which bound bit, so we do not withdraw."""
        beat = _runner(cancelled=(PROD_CANCELLED_MS,), headroom_ms=None)
        assert cmb._level_refuted_by_cancellation(beat) is False

    def test_a_failure_that_is_not_a_cancellation_is_not_a_refutation(self):
        """The counter is written by the real cancel path. A unit that ended
        some other way (an exception, say) leaves it unset, and that is a
        different diagnosis with a different remedy."""
        beat = _runner(cancelled=(PROD_CANCELLED_MS,), record_cancel_counter=False)
        assert cmb._level_refuted_by_cancellation(beat) is False


# =============================================================================
# 3. THE CARRY — the level goes, the progress facts stay
# =============================================================================


class TestTheCarry:
    def test_the_refuted_level_is_withdrawn_and_says_so(self):
        prior = {
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": PROD_UNITS_TOTAL,
                "units_done": PROD_BANKED,
            }
        }
        beat = _production_beat()
        carried = cmb._carry_unit_costs(beat, prior)
        assert "unit_ms" not in carried[PHASE_FUTURES]
        assert carried[PHASE_FUTURES][cmb.LEVEL_REFUTED_KEY] is True
        # Ruling 075: a withdrawal is never silent.
        assert beat.ledger.stages.get(
            f"{cmb.UNIT_COST_REASON_PREFIX}withdrawn_refuted_by_cancellation"
        )

    def test_the_progress_facts_survive_the_withdrawal(self):
        """What a unit COSTS is refuted; how many are banked is not. The
        operator window reads the second and it must not go dark."""
        carried = cmb._carry_unit_costs(_production_beat(), {})
        assert carried[PHASE_FUTURES]["units_done"] == PROD_BANKED
        assert carried[PHASE_FUTURES]["units_total"] == PROD_UNITS_TOTAL

    def test_it_marks_even_when_the_prior_carried_no_futures_entry(self):
        """The ring lives in its own payload key and can set the fence on its
        own. An early return on an absent ``unit_costs`` entry would leave the
        fence exactly as wide as it was and the door exactly as shut."""
        carried = cmb._carry_unit_costs(_production_beat(), {})
        assert carried[PHASE_FUTURES][cmb.LEVEL_REFUTED_KEY] is True

    def test_an_ordinary_beat_is_untouched(self):
        """The control. A beat with a completion carries its level forward the
        way CAL-P163 requires — this repair must not erase what earlier beats
        measured."""
        prior = {
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": PROD_UNITS_TOTAL,
                "units_done": PROD_BANKED,
            }
        }
        beat = _runner(completed=(120_000,))
        carried = cmb._carry_unit_costs(beat, prior)
        assert carried[PHASE_FUTURES]["unit_ms"] == PROD_UNIT_MS
        assert cmb.LEVEL_REFUTED_KEY not in carried[PHASE_FUTURES]


# =============================================================================
# 4. THE RING — a refuted level takes no worst-basis either
# =============================================================================


class TestTheRingIsSuppressed:
    async def test_the_worst_ring_is_not_folded_back_over_a_refuted_level(
        self, monkeypatch
    ):
        """Without this the withdrawal is worse than useless: the ring would
        re-supply 1.5 * 268,898 and the next beat's fence would be 373,347 ms —
        tighter than the 483,000 that had already failed."""
        _fake_carryover(
            monkeypatch,
            unit_costs={
                PHASE_FUTURES: {
                    "units_total": PROD_UNITS_TOTAL,
                    "units_done": PROD_BANKED,
                    cmb.LEVEL_REFUTED_KEY: True,
                }
            },
            ring={PHASE_FUTURES: [PROD_UNIT_WORST_MS]},
        )
        _history, _floors, merged = await cmb.load_phase_measurements()
        assert "unit_ms_worst" not in merged[PHASE_FUTURES]

    async def test_an_unrefuted_level_still_gets_its_ring(self, monkeypatch):
        """The control for the test above — CAL-P163's fold is load-bearing and
        this repair must not disable it generally."""
        _fake_carryover(
            monkeypatch,
            unit_costs={
                PHASE_FUTURES: {
                    "unit_ms": PROD_UNIT_MS,
                    "units_total": PROD_UNITS_TOTAL,
                    "units_done": PROD_BANKED,
                }
            },
            ring={PHASE_FUTURES: [PROD_UNIT_WORST_MS]},
        )
        _history, _floors, merged = await cmb.load_phase_measurements()
        assert merged[PHASE_FUTURES]["unit_ms_worst"] == PROD_UNIT_WORST_MS


def _fake_carryover(monkeypatch, *, unit_costs, ring):
    async def fake(*_args, **_kwargs):
        return {}, {}, unit_costs, ring

    monkeypatch.setattr(cmb, "load_phase_carryover", fake)


# =============================================================================
# 5. THE DOOR OPENS — and closes again the moment a unit completes
# =============================================================================


class TestTheDoorOpens:
    def test_the_next_beats_fence_becomes_the_phase_bound(self):
        """The payoff. With both references withdrawn the fence's own
        no-measurement path applies and the unit gets the PHASE bound — 2.6x
        the 483,000 ms that pinned production, and the widest bound the beat
        has to give."""
        reopened = _ledger_for(
            _plan(unit_ms=None, unit_ms_worst=None, units_done=PROD_BANKED)
        ).statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
        assert reopened == PROD_PHASE_TIMEOUT_MS
        assert reopened > PROD_FENCE_MS

    def test_the_unit_still_cannot_outlive_the_beat(self):
        """The safety property the repair must not spend. Every branch of
        ``statement_timeout_for_unit`` ends at ``min(phase_bound, ...)``, so the
        widened fence is still inner to the phase window."""
        ledger = _ledger_for(_plan(unit_ms=None, unit_ms_worst=None, units_done=PROD_BANKED))
        assert (
            ledger.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
            <= ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=0)
        )

    def test_a_completion_extinguishes_the_marker(self):
        """It is self-limiting: the moment a unit completes at the wider fence,
        ``_unit_costs_from`` builds a fresh level with no marker in it, the ring
        resumes, and the fence re-tightens on an honest measurement."""
        beat = _runner(completed=(600_000,))
        fresh = cmb._unit_costs_from(beat)
        assert fresh[PHASE_FUTURES]["unit_ms"] == 600_000
        assert cmb.LEVEL_REFUTED_KEY not in fresh[PHASE_FUTURES]
