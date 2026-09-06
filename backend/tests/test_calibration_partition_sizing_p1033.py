"""The staged futures partition may only be a size production has FINISHED a unit at
(CAL-P1035, #3536).

THE CLASS OF DEFECT, and this file has now made it twice, in opposite directions.

**First version.** ``STAGED_FUTURES_BUCKETS`` carried a *reasoned* sizing argument
— units get cheaper as they get smaller, so a larger count is the safer direction
— and that argument was never checked against a measured unit cost. At 128 the
build's own gauge reported ``staged:beats_to_publish`` = 81 and then 95, and
``/api/calibration`` served a 29-hour-old ``generated_at`` while the task ran
every hour.

**Second version — the one being repaired here.** The replacement fitted
``cost(B) = P + s_total / B`` through two points and cut the partition to 17. One
of those two points was ``MEASURED_MONOLITH_S = 1350 s``, and this file's own
comment recorded, in the same breath, that the statement it came from was
**cancelled by Postgres** at 1,351,525 ms. A cancellation is not a duration. It is
a *censored* observation: the true cost is that number **or more**, and nobody
knows how much more. Fitting an equality through it pulled the whole curve down,
which understated ``s_total``, overstated the fixed prefix, and therefore
recommended a partition far smaller than anything the measurements supported.

Production refuted it on the first clean beat. **2026-09-06 15:15:00Z**, at B=17,
in an unkilled window (``beat:cancel_cause:incomplete``, elapsed 1,350,702 ms):
one unit was given essentially the entire beat — a 1,137,529 ms statement bound
after a 197,931 ms generation freeze — and **did not finish**. Predicted 882 s;
cancelled still running at 1,138 s. The dial did not merely fail to help, it made
the build unable to bank anything at all.

So the invariant this file pins is not a number, and no longer a model either:

    **a partition may ship only if production has COMPLETED a unit at it**, and
    the model may be used to REJECT sizes, never to endorse one it has not seen.

A censored reading may enter this file as a lower bound and constrain the fit
from one side. It may never be an equality anchor again. Every prediction below
is consequently a LOWER BOUND on cost and an OPTIMISTIC verdict on viability: if
even this model refuses a partition, the partition is refused.

Every constant is a PRODUCTION MEASUREMENT with its source named, and each one
says whether it COMPLETED or was CENSORED. A guard whose expected value is
recomputed from the code it guards agrees by construction and proves nothing.
"""

from __future__ import annotations

import math

import pytest

from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS
from app.tasks.precompute_calibration import (
    STAGED_UNIT_WINDOW_SAFETY,
    _unit_fits_in_window,
)

# --- Production measurements. Source AND completion status named for each. ---

#: COMPLETED. ``staged:unit_ms_mean`` from the ``calibration:main:phase_ledger``
#: durable snapshot written at the end of the 2026-09-06 **12:15Z** beat. That
#: beat ran 1,094 s uninterrupted inside a deliberately quiet merge window,
#: resumed its cursor cleanly, and banked its second unit of 128.
#:
#: This is the WORSE of two completions — the 10:15Z beat measured 723.8 s — and
#: the worse one is used deliberately. The fit sizes a partition against a
#: deadline, so an optimistic unit cost buys a unit that does not fit, and a unit
#: that does not fit banks nothing at all.
MEASURED_UNIT_S_AT_128 = 857.0

#: The partition in force when the reading above was taken.
MEASURED_PARTITION = 128

#: Partition -> the COMPLETED unit costs production has actually observed at it,
#: in seconds. **This is the ship list.** A partition absent from here has never
#: finished a unit in production, so nothing in this file may endorse it,
#: whatever the model says. Both entries are ``staged:unit_ms_mean`` off the
#: phase ledger on 2026-09-06 (10:15Z and 12:15Z), and both are beats whose
#: ``staged:units_completed_this_beat`` was non-zero.
MEASURED_COMPLETIONS: dict[int, tuple[float, ...]] = {128: (723.8, 857.0)}

#: CENSORED — a lower bound, NOT a cost. ``read:futures_unit`` from the
#: 2026-09-06 **15:15:00Z** beat, the first beat to run at B=17 in a window no
#: release interrupted. The unit was cancelled at its own statement bound after
#: 1,137,955 ms with ``staged:units_completed_this_beat`` = 0,
#: ``staged:units_cancelled`` = 1 and ``staged:window_stop:unit_too_large``.
#:
#: cost(17) > this. How much more is unknown and unknowable from that beat: the
#: bound it hit (1,137,529 ms) was the whole rest of the beat, so B=17 cannot be
#: measured by giving it a longer window — there is no longer window to give.
MEASURED_UNIT_S_AT_17_LOWER_BOUND = 1137.955

#: The partition the reading above was taken at.
CENSORED_PARTITION = 17

#: CENSORED — a lower bound, NOT a cost, and the anchor that caused the defect
#: this file is repairing. The pre-staging monolith over the whole ~110K-market
#: roster: one statement, no banking, **cancelled** by Postgres at 1,351,525 ms
#: (#2052, and this module's own 300E rollback notes). It is kept only so the
#: refit can be checked for consistency against it — see
#: :meth:`TestTheCensoredAnchorIsNotAMeasurement`. It is never fitted through.
MEASURED_MONOLITH_S_LOWER_BOUND = 1350.0

#: COMPLETED. ``staged:unit_ms_mean`` (857.0 s) + ``staged:window_left_ms``
#: (287.2 s) off the 12:15Z ledger: what one beat actually had to spend after its
#: fixed setup — which includes the ~200 s ``read:futures_generation`` freeze it
#: pays first. Corroborated at B=17: the 15:15Z beat's freeze cost 197,931 ms and
#: it then handed the unit 1,137,529 ms, i.e. 1,335 s of usable window before the
#: 30 s bound headroom, against 1,144 s of *admissible* window after the 1.25
#: fence.
MEASURED_USABLE_WINDOW_S = 1144.2

# --- The budget. This is the ruling, not a measurement. ----------------------

#: Beats to publish one generation, counted the way the runtime counts them:
#: whole beats, including the following publish beat (see :func:`beats_to_publish`).
#:
#: 8 -> 16 by CERT-2071's repair, 16 -> 24 by CERT-2074's follow-up
#: ``CAL-P1033-WHOLE-UNIT-PUBLISH-BUDGET``. 24 is "within a day of productive
#: beats" — the freshness promise the ship is written against.
#:
#: **UNDER THE REFIT NO PARTITION REACHES IT**, and that is the headline finding
#: rather than a reason to raise it again — see
#: :class:`TestNoPartitionMeetsTheBeatBudget`. The budget stays where the ship's
#: promise put it so that the day the frozen-file repair lands and the fixed
#: prefix falls, that class goes red and says so.
MAX_BEATS_TO_PUBLISH = 24


#: THE ADMISSION CEILING IS NOT OURS TO PICK (CERT-2071's repair). It is
#: ``_unit_fits_in_window``: ``remaining_ms >= reference * STAGED_UNIT_WINDOW_SAFETY``.
#: At the start of a beat ``remaining_ms`` is the whole unit budget and the
#: reference is the previous beat's measured mean, so a partition is viable iff
#: ``cost(B) * STAGED_UNIT_WINDOW_SAFETY <= MEASURED_USABLE_WINDOW_S``.
#:
#: The factor is IMPORTED, so it cannot drift from the code it models.
def admission_ceiling_s() -> float:
    return MEASURED_USABLE_WINDOW_S / STAGED_UNIT_WINDOW_SAFETY


#: The measured beat-to-beat spread of ONE unit at a FIXED partition: 723.8 s
#: (10:15Z) then 857.0 s (12:15Z), both at 128, both completed. +18.4%.
MEASURED_BEAT_TO_BEAT_VARIANCE = (857.0 - 723.8) / 723.8


def fit_cost_model() -> tuple[float, float]:
    """``(fixed_prefix_s, scalable_total_s)``, fitted so that it CANNOT overstate.

    ``cost(B) = P + s_total / B``. Two points determine it, and the two used are
    the completed reading at B=128 and the **censored** reading at B=17 taken at
    its lower bound. Because the B=17 point is a floor, the curve through it is
    the flattest one consistent with the evidence: the real ``s_total`` is larger
    and the real ``P`` smaller than what comes back here.

    That asymmetry is the whole design. Every cost this model predicts is a
    LOWER bound, so every "this partition fits" is optimistic and every "this
    partition does not fit" is certain. The file only ever leans on the second.

    Pure arithmetic over the measurements above — it never reads
    ``STAGED_FUTURES_BUCKETS``, so it cannot quietly agree with whatever that
    constant happens to be.
    """
    s_total = (MEASURED_UNIT_S_AT_17_LOWER_BOUND - MEASURED_UNIT_S_AT_128) / (
        1.0 / CENSORED_PARTITION - 1.0 / MEASURED_PARTITION
    )
    fixed = MEASURED_UNIT_S_AT_128 - s_total / MEASURED_PARTITION
    return fixed, s_total


def predicted_unit_s(buckets: int) -> float:
    """A LOWER BOUND on what one unit costs at this partition. Never a cost."""
    fixed, s_total = fit_cost_model()
    return fixed + s_total / buckets


def predicted_generation_s(buckets: int) -> float:
    return buckets * predicted_unit_s(buckets)


def units_admitted_per_beat(buckets: int) -> int:
    """How many units one STEADY-STATE beat actually banks at this partition.

    CAL-P1033-WHOLE-UNIT-PUBLISH-BUDGET (CERT-2074). This drives production's
    own ``_unit_fits_in_window`` around the shape of the real loop rather than
    dividing a window by a unit cost: the fence is re-consulted before every
    unit, ``remaining_ms`` falls by what the last unit spent, and this beat's
    own worst observation replaces the carried level as soon as there is one.

    Steady state means the carried level IS this partition's own cost — a beat
    that follows a beat at the same size, which is every beat but the first
    after a deploy. The first-after-deploy asymmetry is
    :class:`TestTwoConsecutiveBeatsEachBankAUnit`'s subject.

    The answer is 0 or 1 at every partition (pinned below), which is the whole
    reason the beat budget cannot be a fraction.
    """
    remaining_ms = MEASURED_USABLE_WINDOW_S * 1000.0
    unit_ms = predicted_unit_s(buckets) * 1000.0
    prior_unit_ms = unit_ms
    worst_unit_ms = 0.0
    banked = 0
    while _unit_fits_in_window(
        int(remaining_ms), worst_unit_ms=worst_unit_ms, prior_unit_ms=prior_unit_ms
    ):
        remaining_ms -= unit_ms
        worst_unit_ms = max(worst_unit_ms, unit_ms)
        banked += 1
        if banked > buckets:  # pragma: no cover — a runaway model, not a result
            break
    return banked


def beats_to_publish(buckets: int) -> float:
    """WHOLE beats from a fresh generation to a published one, or ``inf``.

    ``ceil(B / units_per_beat) + 1``. The ``+ 1`` is the publish beat: under
    D45's publish-first order a beat publishes the bank it INHERITS and then
    rebuilds, so the beat that banks the last unit has already published — the
    generation reaches ``/api/calibration`` on the beat after it.

    ``inf`` when a beat banks nothing: the build never publishes at all, which
    is a different and worse fact than a large count (production's own gauge
    says ``-1`` for the same case, and for the same reason). **B=17 is ``inf``,
    and that is not a projection — production spent a whole clean beat proving
    it on 2026-09-06 at 15:15Z.**
    """
    per_beat = units_admitted_per_beat(buckets)
    if per_beat < 1:
        return math.inf
    return math.ceil(buckets / per_beat) + 1


def gauge_projected_beats(buckets: int) -> float:
    """What production's ``staged:beats_to_publish`` REPORTS — not what it costs.

    ``_record_convergence_projection`` computes ``usable_ms / unit_ms_mean`` and
    divides the remaining units by it, so a beat that measures 1.3 units of
    window is credited with 1.3 units of progress. It cannot bank 0.3 of a unit.

    Kept, and named for what it is, because it is the quantity the 12:15Z ledger
    reading of 95 can be checked against. It is NOT the budget: compare it with
    :func:`beats_to_publish` and the gap is the defect CERT-2074 named.
    """
    return predicted_generation_s(buckets) / MEASURED_USABLE_WINDOW_S


def admission_margin(buckets: int) -> float:
    """How far a partition sits under the production gate, as a fraction.

    Negative means the gate refuses the next beat's first unit. Optimistic, like
    everything derived from the fit: the true margin is smaller.
    """
    return admission_ceiling_s() / predicted_unit_s(buckets) - 1.0


def max_achievable_margin() -> float:
    """The best any partition can do — the B -> inf limit, i.e. the fixed prefix.

    Derived, not chosen. It is the ceiling on every safety argument in this file.
    """
    fixed, _ = fit_cost_model()
    return admission_ceiling_s() / fixed - 1.0


def model_admits(buckets: int) -> bool:
    """Whether the OPTIMISTIC model lets a unit of this size through the gate.

    A necessary condition for shipping a partition, never a sufficient one —
    :data:`MEASURED_COMPLETIONS` supplies the sufficient half.
    """
    return predicted_unit_s(buckets) <= admission_ceiling_s()


class TestTheCensoredAnchorIsNotAMeasurement:
    """The defect class, pinned: never fit an equality through a cancellation.

    This is the guard firing on the code that shipped. B=17 was live in master
    from 14:12Z to the next release on 2026-09-06, chosen by a search over a fit
    anchored on a cancelled statement. Every assertion here would have been red
    on that tree.
    """

    @staticmethod
    def _refuted_fit() -> tuple[float, float]:
        """The fit exactly as CAL-P1033 wrote it, reproduced to be refuted."""
        s_total = (MEASURED_MONOLITH_S_LOWER_BOUND - MEASURED_UNIT_S_AT_128) / (
            1.0 - 1.0 / MEASURED_PARTITION
        )
        return MEASURED_MONOLITH_S_LOWER_BOUND - s_total, s_total

    def test_production_refutes_the_monolith_anchored_fit(self):
        """882 s predicted; still running, and cancelled, at 1,138 s."""
        fixed, s_total = self._refuted_fit()
        refuted_prediction = fixed + s_total / CENSORED_PARTITION
        assert refuted_prediction < MEASURED_UNIT_S_AT_17_LOWER_BOUND, (
            f"the monolith-anchored fit predicts {refuted_prediction:.0f}s at "
            f"B={CENSORED_PARTITION}, which production has NOT exceeded — the "
            f"refutation this file is built on has stopped holding, so re-derive "
            f"before trusting anything below"
        )

    def test_the_refutation_is_large_enough_to_be_a_finding(self):
        """Not a rounding gap: the floor alone is 29% above the prediction."""
        fixed, s_total = self._refuted_fit()
        refuted_prediction = fixed + s_total / CENSORED_PARTITION
        understatement = MEASURED_UNIT_S_AT_17_LOWER_BOUND / refuted_prediction - 1.0
        assert understatement > 0.20, (
            f"the old fit understates the B={CENSORED_PARTITION} floor by only "
            f"{understatement:+.1%}; below 20% this stops being a modelling "
            f"defect and starts being beat-to-beat noise"
        )

    def test_the_refit_is_consistent_with_every_censored_reading(self):
        """A lower bound constrains from one side only — and both are satisfied.

        The refit predicts 6,322 s for the monolith. That is not a claim the
        monolith takes 6,322 s; it is the statement that a cancellation at
        1,350 s tells us nothing that contradicts it, which is precisely what
        the first version of this file forgot.
        """
        assert predicted_unit_s(1) > MEASURED_MONOLITH_S_LOWER_BOUND
        # The B=17 floor is an ANCHOR, so the curve passes exactly through it.
        # That is the flattest curve the evidence permits, not a claim that 17
        # costs 1,138 s — it costs that or more.
        assert predicted_unit_s(CENSORED_PARTITION) == pytest.approx(
            MEASURED_UNIT_S_AT_17_LOWER_BOUND, abs=0.5
        )

    def test_the_refit_still_reproduces_the_one_completed_point(self):
        assert predicted_unit_s(MEASURED_PARTITION) == pytest.approx(
            MEASURED_UNIT_S_AT_128, abs=0.5
        )


class TestWhatTheFitSaysNowThatItIsHonest:
    """The corrected finding, which is not the one the first version asserted."""

    def test_the_per_unit_cost_is_NOT_prefix_dominated(self):
        """The claim that produced B=17, stated so its failure is visible.

        CAL-P1033 asserted ``fixed > s_total`` and called it "the finding
        itself". Under the censored anchor that was 853 vs 497. Honestly fitted
        it is 814 vs 5,508 — the scalable term is nearly seven times the prefix,
        so shrinking the partition buys a great deal more work per unit, which
        is exactly what the 15:15Z beat felt.
        """
        fixed, s_total = fit_cost_model()
        assert s_total > fixed, (
            f"the scalable term {s_total:.0f}s has fallen back under the fixed "
            f"prefix {fixed:.0f}s — the pre-CAL-P1035 sizing argument would be "
            f"live again and the partition must be re-derived from scratch"
        )

    def test_the_AGGREGATE_work_is_prefix_dominated_at_the_shipping_size(self):
        """Both things are true at once, and conflating them is what went wrong.

        Per unit the prefix is the smaller half. Across a whole generation it is
        paid B times over, so at the shipping partition it is the overwhelming
        majority of the total — 104,000 s against 5,500 s. That is the fact that
        makes the frozen-file repair the only real lever, and it is a statement
        about the GENERATION, never about one unit.
        """
        fixed, s_total = fit_cost_model()
        assert STAGED_FUTURES_BUCKETS * fixed > s_total

    def test_the_smallest_partition_the_model_admits_is_itself_a_lower_bound(self):
        """55, and the true answer is larger because the model is optimistic."""
        smallest = next(b for b in range(1, 1025) if model_admits(b))
        assert smallest == 55, (
            f"the optimistic model now admits B={smallest}; the shipping rule "
            f"below is unaffected (it ships only measured sizes) but this number "
            f"is quoted in the D80 scope note and should be re-quoted"
        )
        assert not model_admits(smallest - 1)


class TestThePartitionInForceHasBeenMeasured:
    """THE SHIPPING RULE. Both clauses, and each one rejects something.

    Ship the smallest partition that (a) the optimistic model admits AND (b)
    production has COMPLETED a unit at. (a) alone is what shipped B=17 and lost
    a day. (b) alone would let a size through that provably cannot be admitted.
    """

    def test_the_shipped_value_is_the_ONE_THE_RULE_PICKS(self):
        picked = next(
            (b for b in sorted(MEASURED_COMPLETIONS) if model_admits(b)), None
        )
        assert picked is not None, (
            "no partition with a measured completion is admissible — the build "
            "cannot bank at ANY size we have evidence for; this is the "
            "frozen-file repair (D80), not a dial"
        )
        assert STAGED_FUTURES_BUCKETS == picked, (
            f"the rule picks {picked} (margin {admission_margin(picked):+.2%}), "
            f"but {STAGED_FUTURES_BUCKETS} ships"
        )

    def test_clause_b_is_load_bearing_and_rejects_a_size_the_model_likes(self):
        """64 passes the model at +1.7% and has never finished a unit.

        Without clause (b) the rule would pick it — an extrapolation, from a
        model whose last extrapolation cost a day of staleness, into a region
        where the only two production readings are a completion at 128 and a
        cancellation at 17.
        """
        assert model_admits(64)
        assert 64 not in MEASURED_COMPLETIONS

    def test_clause_a_is_load_bearing_and_rejects_the_size_that_shipped(self):
        assert not model_admits(CENSORED_PARTITION)

    def test_one_unit_still_fits_one_beat(self):
        unit_s = predicted_unit_s(STAGED_FUTURES_BUCKETS)
        ceiling = admission_ceiling_s()
        assert unit_s <= ceiling, (
            f"a unit at {STAGED_FUTURES_BUCKETS} buckets costs at least "
            f"{unit_s:.0f}s against the production gate's {ceiling:.0f}s ceiling "
            f"— the fence will refuse the next beat's FIRST unit and the build "
            f"banks nothing, which is the 15:15Z state"
        )

    def test_the_partition_is_a_usable_count(self):
        assert isinstance(STAGED_FUTURES_BUCKETS, int)
        assert STAGED_FUTURES_BUCKETS >= 1


class TestNoPartitionMeetsTheBeatBudget:
    """The headline finding, and the assertion that will go red when D80 lands.

    The budget is the ship's freshness promise: one generation inside 24 whole
    beats. Under an honest fit NOTHING reaches it — the admissible sizes all
    start at 55 and cost B+1 beats. The dial is exhausted. Only bringing the
    fixed prefix down can satisfy the promise, and that lives in
    ``_futures_population_sql`` in ruling-D45-frozen ``precompute_calibration.py``.
    """

    def test_every_partition_misses_the_budget(self):
        best = min(
            (beats_to_publish(b) for b in range(1, 513)), default=math.inf
        )
        assert best > MAX_BEATS_TO_PUBLISH, (
            f"some partition now publishes in {best} whole beats, inside the "
            f"{MAX_BEATS_TO_PUBLISH}-beat budget — the fixed prefix has come "
            f"down, the D80 repair has effectively landed, and the partition "
            f"should be re-derived with the new headroom"
        )

    def test_the_cheapest_admissible_partition_is_named_not_implied(self):
        """56 beats at B=55: what the best possible dial setting would cost."""
        admissible = [b for b in range(1, 513) if model_admits(b)]
        cheapest = min(beats_to_publish(b) for b in admissible)
        assert cheapest == 56
        assert cheapest > MAX_BEATS_TO_PUBLISH

    def test_the_shipping_partition_costs_what_it_costs(self):
        assert beats_to_publish(STAGED_FUTURES_BUCKETS) == 129


class TestTheGuardFiresOnTheCodeThatShipped:
    """A guard that cannot fail a historical value is not a guard."""

    def test_the_partition_that_shipped_this_morning_banks_nothing(self):
        """B=17 is ``inf``, matching what the 15:15Z beat did in production."""
        assert units_admitted_per_beat(CENSORED_PARTITION) == 0
        assert beats_to_publish(CENSORED_PARTITION) == math.inf

    @pytest.mark.parametrize("buckets", [2, 5, 8, 17, 32, 54])
    def test_the_gate_refuses_every_partition_below_the_admissible_floor(
        self, buckets
    ):
        """8 and 17 are the two the refuted fit endorsed; 54 is the boundary."""
        assert not model_admits(buckets)
        assert beats_to_publish(buckets) == math.inf

    def test_the_historical_value_projects_the_number_production_reported(self):
        """128 -> ~96 beats, which is the gauge production actually wrote.

        The independent check on the whole model: ``staged:beats_to_publish``
        was read off the live 12:15Z ledger as **95** with 2 of 128 units
        banked, and the fit was built from a unit cost and a window, never from
        that gauge. Reality at 128 is 129 whole beats, and the 33-beat gap is
        not rounding — it is the gauge crediting a beat with 1.3 units of
        progress it cannot bank.
        """
        beats = gauge_projected_beats(128)
        assert 90 <= beats <= 101, f"model projects {beats:.0f} beats, ledger said 95"

    def test_the_window_ceiling_rejects_a_partition_that_would_deadlock(self):
        """The other direction: too FEW buckets is its own failure mode.

        B=1 is the monolith. The gauge would happily accept it at 5.5 beats,
        which is what made this test necessary. Counting whole beats (CERT-2074)
        catches it — a beat banking nothing is ``inf``.
        """
        assert predicted_unit_s(1) > admission_ceiling_s()
        assert gauge_projected_beats(1) <= MAX_BEATS_TO_PUBLISH
        assert beats_to_publish(1) == math.inf


class TestABeatBanksAtMostOneUnit:
    """CERT-2074's follow-up: the budget counts WHOLE beats, because runtime does.

    Two units never fit one beat at ANY partition, so a generation costs B
    productive beats and then the publish beat: **B + 1**.

    Derived here, not asserted: the count comes from driving production's own
    fence, so if the fence or the cost model moves, the ``+ 1`` moves with it.
    """

    def test_no_partition_ever_fits_two_units_in_one_beat(self):
        """Two units need ``window >= 2.25 x unit``. Even the B -> inf floor on
        unit cost — the fixed prefix, which no partition can go below — is far
        above the ``window / 2.25`` that would allow it.
        """
        fixed, _ = fit_cost_model()
        two_unit_ceiling_s = MEASURED_USABLE_WINDOW_S / (1.0 + STAGED_UNIT_WINDOW_SAFETY)
        assert fixed > two_unit_ceiling_s, (
            f"the fixed prefix has fallen to {fixed:.0f}s, under the "
            f"{two_unit_ceiling_s:.0f}s at which a beat could bank two units — "
            f"the +1-per-unit beat model no longer holds and every projection "
            f"in this file must be re-derived"
        )
        worst = max(
            (units_admitted_per_beat(b) for b in range(1, MEASURED_PARTITION + 1)),
            default=0,
        )
        assert worst <= 1, f"some partition banks {worst} units in one beat"

    def test_the_shipping_partition_costs_one_beat_per_unit_plus_the_publish_beat(self):
        assert units_admitted_per_beat(STAGED_FUTURES_BUCKETS) == 1
        assert beats_to_publish(STAGED_FUTURES_BUCKETS) == STAGED_FUTURES_BUCKETS + 1

    def test_the_gauge_under_reports_what_the_shipped_partition_costs(self):
        gauge = gauge_projected_beats(STAGED_FUTURES_BUCKETS)
        real = beats_to_publish(STAGED_FUTURES_BUCKETS)
        assert gauge < real, (
            "the gauge no longer under-reports — production's projection has "
            "been made whole-unit and this file should read it directly"
        )


class TestTwoConsecutiveBeatsEachBankAUnit:
    """CERT-2071's required regression, driven through the REAL gate.

    The BLOCK's finding was not that 5 is slow — it is that the production
    admission rule REFUSES the beat after the first new-size unit completes, so
    the build alternates between a productive beat and a self-blocked one and
    the "beats to publish" arithmetic silently doubles. A partition is only
    shippable if TWO CONSECUTIVE beats each admit a unit.

    These call ``_unit_fits_in_window`` itself — production's own predicate,
    with production's own ``STAGED_UNIT_WINDOW_SAFETY`` — rather than restating
    its inequality.
    """

    @staticmethod
    def _two_beats(buckets: int, carried_level_s: float) -> tuple[bool, bool]:
        """``(beat 1 admitted, beat 2 admitted)`` at a partition.

        Beat 1 opens with the level carried from the PREVIOUS partition's beats
        (nothing at this size has run yet) and, if it is admitted, ends having
        measured this size's own cost. Beat 2 opens on that new level.
        """
        window_ms = MEASURED_USABLE_WINDOW_S * 1000.0
        new_cost_ms = predicted_unit_s(buckets) * 1000.0

        beat1 = _unit_fits_in_window(
            window_ms, worst_unit_ms=0.0, prior_unit_ms=carried_level_s * 1000.0
        )
        beat2 = _unit_fits_in_window(
            window_ms, worst_unit_ms=0.0, prior_unit_ms=new_cost_ms
        )
        return beat1, beat2

    def test_the_shipping_partition_admits_a_unit_on_two_consecutive_beats(self):
        beat1, beat2 = self._two_beats(
            STAGED_FUTURES_BUCKETS, carried_level_s=MEASURED_UNIT_S_AT_128
        )
        assert beat1, "the deploy beat is refused before it measures anything"
        assert beat2, (
            f"B={STAGED_FUTURES_BUCKETS} banks a unit and then BLOCKS ITSELF: "
            f"{predicted_unit_s(STAGED_FUTURES_BUCKETS):.0f}s x "
            f"{STAGED_UNIT_WINDOW_SAFETY} exceeds the "
            f"{MEASURED_USABLE_WINDOW_S:.0f}s budget, so beat two refuses its "
            f"first unit — progress alternates and the beat count doubles"
        )

    @pytest.mark.parametrize("buckets", [2, 4, 5, 6, 7, 17])
    def test_it_fails_on_beat_two_for_every_partition_the_block_named(self, buckets):
        """The falsifier, run against the values this guard must reject.

        5 is the one CERT-2071 caught on the exact SHA; **17 is the one
        production caught on 2026-09-06 at 15:15Z**, and it belongs here because
        it is the same shape of failure — admitted on beat one against the
        carried 128-era level, refused thereafter on its own measurement.
        """
        beat1, beat2 = self._two_beats(buckets, carried_level_s=MEASURED_UNIT_S_AT_128)
        assert beat1, "setup is wrong: beat one should be admitted on the old level"
        assert not beat2, (
            f"B={buckets} now survives beat two — the model or the gate moved, "
            f"and the partition choice must be re-derived before trusting this"
        )


class TestNoPartitionIsComfortable:
    """The finding that outlives whatever number ships, stated as assertions.

    It is the reason CERT-2071's "choose a partition with defensible real
    margin" cannot be satisfied by a dial at all, and the reason the frozen-file
    repair is required rather than optional.
    """

    def test_the_headroom_above_the_prefix_is_smaller_than_the_measured_spread(self):
        """The derived form of "no partition is comfortable".

        Every partition's margin is bought out of the gap between the fixed
        prefix and the admission ceiling — 101 s. One unit at a FIXED partition
        was measured moving 723.8 s -> 857.0 s, which is 150 s at the prefix.
        The spread is larger than the entire budget for margin, so a self-block
        can happen at any size. Both sides are measurements; neither is a bar
        anyone picked.
        """
        fixed, _ = fit_cost_model()
        headroom_s = admission_ceiling_s() - fixed
        spread_s = MEASURED_BEAT_TO_BEAT_VARIANCE * fixed
        assert headroom_s < spread_s, (
            f"headroom above the prefix is now {headroom_s:.0f}s against a "
            f"measured spread of {spread_s:.0f}s — the build has become "
            f"schedulable and this file's pessimism should be revisited"
        )

    def test_beat_to_beat_variance_exceeds_the_best_achievable_margin(self):
        """The same statement as a ratio, against the B -> inf margin ceiling."""
        assert MEASURED_BEAT_TO_BEAT_VARIANCE > max_achievable_margin(), (
            f"variance {MEASURED_BEAT_TO_BEAT_VARIANCE:+.1%} is now inside the "
            f"achievable margin {max_achievable_margin():+.1%} — the build has "
            f"become schedulable and this file's pessimism should be revisited"
        )
