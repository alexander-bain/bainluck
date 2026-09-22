"""CAL-P1335 (#6868) — the admission fence asks a candidate its own size.

THE SHIP: the accuracy page stops waiting on beats that throw half their window
away. ``/api/calibration`` has served a ``generated_at`` of 2026-09-15T11:16:10Z
for seven days because the staged futures build banks ~1 unit an hour, and it
banks ~1 an hour because of the defect below — not because the work is that big.

WHAT PRODUCTION SAID, ``calibration:main:phase_ledger`` read 2026-09-22 11:29Z:

* ``read:futures_unit`` 827,901 ms for **one** unit, against a ``futures``
  budget of 1,283,522 ms.
* ``staged:window_left_ms`` **497,980** — 39% of the window, unspent.
* ``staged:window_stop:unit_too_large``, ``staged:units_banked`` 109 of 203.
* The cursor at that moment held ``unit_splits`` for 36 slots, cut 2x (21), 3x
  (6), 4x (4), 5x (2), 7x (2) and 11x (1) — **111 children** beside 92 whole
  slots, and every one of the 94 unbanked units was one of those children.

So the beat had 497,980 ms in hand and 94 candidates, the smallest of them a
1/11th slice, and it asked none of them what they cost. The fence compared each
to ``max(this beat's worst, last beat's mean)`` — 827,901 ms — and the loop
``break``-ed on the first refusal, which in a uniform plan is sound and in a
refined one is a scale error.

That is refinement not paying. ``refine_unit`` exists to cut a slot so more of
them fit in a window; the fence then refused the children on the strength of
their parent, so the build paid for every split and collected on none.

THE SCALE IS MEASURED, NOT ASSUMED. ``calibration_main_build`` carries the
two-point read that settles it: slot ``128:119`` cancelled at a floor of
>= 1,256,075 ms, and its child ``256:119`` COMPLETED in 635,125 ms — 50.6% of
the parent's floor, so ``prefix = 2*cost(2B) - cost(B) <= 14,175 ms``. Cost is
essentially pure ``scalable/B``. Half the questions, half the time.

WHAT IS DELIBERATELY NOT CLAIMED HERE. Rescaling can under-estimate a candidate
— a slot can be dear for reasons other than its size. The cost of being wrong is
bounded and already paid for: the unit's statement bound is capped by the phase
budget (:meth:`PhaseLedger.statement_timeout_for_unit` returns ``phase_bound``
whenever the unit basis exceeds it), so an over-admitted unit cannot outlive the
window; it cancels, ``note_unit_cancelled`` remembers it, ``attempt_order``
defers it and ``refine_unit`` cuts it. That is the build's existing recovery
path, and a cancellation on a rescaled admission walks it.
"""

from __future__ import annotations

import pytest

from app.tasks.precompute_calibration import (
    STAGED_UNIT_WINDOW_SAFETY,
    _unit_fits_in_window,
)

#: The 11:29Z beat, in the units the fence actually reads.
PRODUCTION_WORST_MS = 827_901
PRODUCTION_WINDOW_LEFT_MS = 497_980
#: A whole ``buckets=128`` slot and the finest child the cursor held (11x).
WHOLE_SLOT_VMS = 220
FINEST_CHILD_VMS = 20


class TestTheFenceIsUnchangedWithoutSizes:
    """Every pre-CAL-P1335 caller gets the pre-CAL-P1335 predicate.

    Stated first because it is the claim the whole change rests on: the new
    arguments all default to zero, and a reference with no size attached is a
    reference that cannot be rescaled. "We cannot tell how big this unit is"
    must decline exactly where it declined yesterday, never admit on the
    strength of a measurement nobody took.
    """

    def test_a_refusal_with_no_sizes_is_still_a_refusal(self):
        assert not _unit_fits_in_window(
            PRODUCTION_WINDOW_LEFT_MS, PRODUCTION_WORST_MS, 726_124
        )

    def test_an_admission_with_no_sizes_is_still_an_admission(self):
        assert _unit_fits_in_window(1_283_522, PRODUCTION_WORST_MS, 726_124)

    def test_the_candidate_size_alone_does_nothing(self):
        """A candidate size with no REFERENCE size is not a ratio.

        The guard that matters most: half the pair is not a measurement, and
        reading it as one would rescale by an arbitrary count.
        """
        assert not _unit_fits_in_window(
            PRODUCTION_WINDOW_LEFT_MS,
            PRODUCTION_WORST_MS,
            726_124,
            candidate_vms=FINEST_CHILD_VMS,
        )

    def test_a_reference_size_alone_does_nothing(self):
        assert not _unit_fits_in_window(
            PRODUCTION_WINDOW_LEFT_MS,
            PRODUCTION_WORST_MS,
            726_124,
            worst_unit_vms=WHOLE_SLOT_VMS,
            prior_unit_vms=WHOLE_SLOT_VMS,
        )

    def test_no_window_left_is_still_refused_however_small_the_candidate(self):
        """``remaining_ms <= 0`` short-circuits ahead of every rescaling."""
        assert not _unit_fits_in_window(
            0,
            PRODUCTION_WORST_MS,
            726_124,
            candidate_vms=1,
            worst_unit_vms=WHOLE_SLOT_VMS,
            prior_unit_vms=WHOLE_SLOT_VMS,
        )

    def test_no_reference_at_all_still_admits(self):
        """CAL-P1033's mechanism: ``reference <= 0`` admits unconditionally."""
        assert _unit_fits_in_window(
            1, 0.0, 0.0, candidate_vms=WHOLE_SLOT_VMS, worst_unit_vms=WHOLE_SLOT_VMS
        )


class TestTheProductionBeatWouldHaveBankedMore:
    """The specimen, driven through the real predicate.

    Not a model of the fence — the fence itself, handed the numbers the
    11:29Z beat held.
    """

    def test_the_finest_child_was_refused_before_this_change(self):
        """94 candidates, 497,980 ms, and the beat asked none of them."""
        assert not _unit_fits_in_window(
            PRODUCTION_WINDOW_LEFT_MS, PRODUCTION_WORST_MS, 726_124
        ), (
            "the size-blind fence now admits the 11:29Z candidate — the "
            "specimen this file is built on has stopped reproducing, so the "
            "before-state is no longer what the docstring claims"
        )

    def test_the_finest_child_is_admitted_once_the_fence_knows_its_size(self):
        """20 questions against a 220-question reference: 75,264 ms expected."""
        assert _unit_fits_in_window(
            PRODUCTION_WINDOW_LEFT_MS,
            PRODUCTION_WORST_MS,
            726_124,
            candidate_vms=FINEST_CHILD_VMS,
            worst_unit_vms=WHOLE_SLOT_VMS,
            prior_unit_vms=WHOLE_SLOT_VMS,
        )

    def test_a_whole_slot_is_STILL_refused_at_the_same_moment(self):
        """The fence did not merely get looser — it got specific.

        The same window, the same references, a candidate the size of the
        reference: refused, exactly as before. A change that admitted this too
        would be a fence with the safety factor removed, which is a different
        and much worse change wearing this one's clothes.
        """
        assert not _unit_fits_in_window(
            PRODUCTION_WINDOW_LEFT_MS,
            PRODUCTION_WORST_MS,
            726_124,
            candidate_vms=WHOLE_SLOT_VMS,
            worst_unit_vms=WHOLE_SLOT_VMS,
            prior_unit_vms=WHOLE_SLOT_VMS,
        )

    def test_a_candidate_LARGER_than_the_reference_is_NOT_refused_sooner(self):
        """The clamp, and it is the safety property of the whole change.

        An above-average candidate rescales UP, and the intuitive thing is to
        let it: bigger unit, bigger expectation. That is the version this file
        shipped first and the 6599 simulator refuted it in one run — the build
        banked every below-mean slot and then never published, because a unit
        refused at the START of a beat is refused at the largest window it will
        ever see, and nothing later shrinks it. ``refine_unit`` is the only
        thing that does, and it fires on a CANCELLATION, which requires the unit
        to have been admitted first. Tightening does not defer a unit, it
        strands it.

        So rescaling is clamped to a widening, and the consequence is worth
        stating as its own assertion: **every unit the size-blind fence admits
        is still admitted.** Whatever else this change does, it cannot stop
        something running that runs today.
        """
        window = int(PRODUCTION_WORST_MS * STAGED_UNIT_WINDOW_SAFETY) + 1
        assert _unit_fits_in_window(
            window,
            PRODUCTION_WORST_MS,
            0.0,
            candidate_vms=WHOLE_SLOT_VMS,
            worst_unit_vms=WHOLE_SLOT_VMS,
        )
        assert _unit_fits_in_window(
            window,
            PRODUCTION_WORST_MS,
            0.0,
            candidate_vms=WHOLE_SLOT_VMS * 2,
            worst_unit_vms=WHOLE_SLOT_VMS,
        ), (
            "a double-size candidate was refused in a window the size-blind "
            "fence admits — the clamp has gone and the fence can now strand a "
            "unit that no later beat can make smaller"
        )

    @pytest.mark.parametrize("candidate_vms", [1, 20, 219, 220, 221, 440, 10_000])
    def test_no_candidate_size_can_refuse_what_the_blind_fence_admits(
        self, candidate_vms
    ):
        """The widening property, swept rather than spot-checked.

        Across the boundary in both directions: if the size-blind predicate
        says yes, the size-aware one says yes, whatever the candidate's size.
        """
        window = int(PRODUCTION_WORST_MS * STAGED_UNIT_WINDOW_SAFETY) + 1
        assert _unit_fits_in_window(window, PRODUCTION_WORST_MS, 726_124)
        assert _unit_fits_in_window(
            window,
            PRODUCTION_WORST_MS,
            726_124,
            candidate_vms=candidate_vms,
            worst_unit_vms=WHOLE_SLOT_VMS,
            prior_unit_vms=WHOLE_SLOT_VMS,
        )


class TestTheTwoReferencesAreRescaledApart:
    """``max`` of two rates, never one rescaling of a ``max``.

    ``worst_unit_ms`` and ``prior_unit_ms`` are costs of two different units and
    may be measured at two different granularities — the beat's worst is a slot
    this hour, the carried mean is an average over last hour's plan. Maxing the
    raw milliseconds first and rescaling the winner divides one slot's cost by
    another slot's question count, which is the very error this change exists to
    remove, committed one level up.
    """

    def test_the_dearer_QUESTION_wins_even_when_it_is_the_cheaper_UNIT(self):
        """A small, dear unit must beat a large, cheap one.

        ``worst`` is the bigger number (200,000 > 100,000) but describes 100
        questions — 2,000 ms each. ``prior`` is smaller and describes 10 — 10,000
        ms each. A 10-question candidate costs 100,000 ms on the prior rate and
        20,000 ms on the worst rate; the fence must use 100,000.
        """
        window = int(50_000 * STAGED_UNIT_WINDOW_SAFETY)
        assert not _unit_fits_in_window(
            window,
            200_000,
            100_000,
            candidate_vms=10,
            worst_unit_vms=100,
            prior_unit_vms=10,
        ), (
            "the fence took the larger millisecond figure and rescaled that — "
            "the cheaper-per-question reference won and a dear candidate was "
            "admitted into a window a third its size"
        )

    def test_one_sized_reference_does_not_disable_the_other(self):
        """An unsized reference keeps its raw value and still competes.

        The conservative reading: a reference we cannot rescale is not
        discarded, it is used as-is. Here the unsized ``prior`` is what refuses
        the candidate, and dropping it would admit on the rescaled ``worst``.
        """
        assert not _unit_fits_in_window(
            300_000,
            800_000,
            400_000,
            candidate_vms=10,
            worst_unit_vms=100,
            prior_unit_vms=0.0,
        )


class TestTheRateIsTheMeasuredOne:
    """Halving the questions halves the expectation — the 2026-09-19 read."""

    @pytest.mark.parametrize("factor", [2, 3, 4, 5, 7, 11])
    def test_a_child_cut_by_factor_n_is_expected_to_cost_a_factor_n_less(
        self, factor
    ):
        """The six split factors the live cursor actually held.

        Driven as a boundary pair at each factor rather than a spot check, so
        the assertion is about the arithmetic and not about one lucky window.
        """
        reference_ms = 660_000.0
        expected = reference_ms / factor
        just_enough = expected * STAGED_UNIT_WINDOW_SAFETY
        kwargs = {
            "candidate_vms": WHOLE_SLOT_VMS // factor,
            "worst_unit_vms": WHOLE_SLOT_VMS // factor * factor,
        }
        assert _unit_fits_in_window(int(just_enough) + 1, reference_ms, 0.0, **kwargs)
        assert not _unit_fits_in_window(
            int(just_enough) - 1, reference_ms, 0.0, **kwargs
        )
