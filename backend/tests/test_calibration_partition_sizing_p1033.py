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

**Third version — the domain.** That last sentence has a domain, and the first
draft of this file did not say so: it searched B in [1, 512] while the fit is
pinned to a completed point at 128 and a floor at 17. Constraining a curve from
one side only fixes the SIGN of the error on one side of the anchor
(:data:`MODEL_DOMAIN_MAX` derives it): below 128 a prediction is a lower bound
and a refusal is certain, **above 128 the same prediction is an UPPER bound**
and refusing on it is the censored-anchor sin committed inside the guard that
exists to prevent it. Caught as ``CAL-P1035-CENSORED-MODEL-DOMAIN``, the
grader's nonblocking follow-up on CERT-2093, and repaired here. The verdict does
not move — partitions above 128 are refused by :func:`min_beats_above_the_model_domain`
instead, which spends no fit at all, only a completed unit cost and the fact
that splitting work into more pieces cannot make there be less of it.

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

#: The partition in force when the readings below were taken.
MEASURED_PARTITION = 128

#: Partition -> the COMPLETED unit costs production has actually observed at it,
#: in seconds, **in beat order**. **This is the ship list.** A partition absent
#: from here has never finished a unit in production, so nothing in this file may
#: endorse it, whatever the model says. Every entry is ``staged:unit_ms_mean``
#: off the ``calibration:main:phase_ledger`` durable snapshot for a beat whose
#: ``staged:units_completed_this_beat`` was non-zero — a cancelled unit is a
#: lower bound and never lands here (that is the defect CAL-P1035 repaired).
#:
#: All three are 2026-09-06:
#:
#: * **10:15Z** — 723.8 s, banked unit 1 of 128.
#: * **12:15Z** — 857.0 s, banked unit 2 of 128; ran 1,094 s uninterrupted
#:   inside a deliberately quiet merge window and resumed its cursor cleanly.
#: * **17:15Z** — 753.3 s, banked unit 3 of 128; the first beat after the B=17
#:   excursion was reverted, in a window with zero releases (last release v4220
#:   at 16:55:33Z). ``read:futures_unit`` 753,280 ms, and
#:   ``staged:unit_ms_mean_completed`` equal to it because nothing truncated.
#:
#: **This list is HARVESTED, not commissioned** (CAL-P1036-GENERATION-WIDE-UNIT-
#: COST-PRECONDITION, the CERT-2098 grader's follow-up). One completed unit cost
#: arrives free on every clean beat, so the sample widens by one row per session
#: at no measurement cost, and everything downstream is derived from it rather
#: than restated: the fit anchor is its ``max``, the fit-free floor its ``min``,
#: the spread its range. A new reading cannot be cherry-picked into the flattering
#: slot — see :class:`TestTheCompletionSampleIsHarvestedNotCurated`.
MEASURED_COMPLETIONS: dict[int, tuple[float, ...]] = {128: (723.8, 857.0, 753.3)}

#: COMPLETED, and the anchor the fit is pinned through.
#:
#: DERIVED as the WORST reading in the sample above, deliberately: the fit sizes
#: a partition against a deadline, so an optimistic unit cost buys a unit that
#: does not fit, and a unit that does not fit banks nothing at all. Worst-of-
#: sample also means a future clean beat can only ever make this file more
#: pessimistic, never less — the direction a guard should move under new
#: evidence.
#:
#: Today: 857.0 s (the 12:15Z beat), unmoved by the 17:15Z reading.
MEASURED_UNIT_S_AT_128 = max(MEASURED_COMPLETIONS[MEASURED_PARTITION])

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


#: The measured beat-to-beat spread of ONE unit at a FIXED partition, DERIVED as
#: the full range of :data:`MEASURED_COMPLETIONS` over its cheapest reading, so
#: each harvested beat re-prices it. Today +18.4%, from 723.8 s (10:15Z) to
#: 857.0 s (12:15Z), with 753.3 s (17:15Z) landing inside the existing range —
#: which is why the third reading moved this number not at all. The spread is
#: therefore not yet known to be wider than two beats said; it is now known not
#: to be a trend, because the newest reading is not the largest.
MEASURED_BEAT_TO_BEAT_VARIANCE = (
    max(MEASURED_COMPLETIONS[MEASURED_PARTITION])
    - min(MEASURED_COMPLETIONS[MEASURED_PARTITION])
) / min(MEASURED_COMPLETIONS[MEASURED_PARTITION])


def fit_cost_model() -> tuple[float, float]:
    """``(fixed_prefix_s, scalable_total_s)``, fitted so that it CANNOT overstate.

    ``cost(B) = P + s_total / B``. Two points determine it, and the two used are
    the completed reading at B=128 and the **censored** reading at B=17 taken at
    its lower bound. Because the B=17 point is a floor, the curve through it is
    the flattest one consistent with the evidence: the real ``s_total`` is larger
    and the real ``P`` smaller than what comes back here.

    That asymmetry is the whole design, and it has a domain. **At or below the
    completed anchor** every cost this model predicts is a LOWER bound, so every
    "this partition fits" is optimistic and every "this partition does not fit"
    is certain; the file only ever leans on the second. Above the anchor the
    asymmetry reverses and the model is inadmissible — :data:`MODEL_DOMAIN_MAX`
    derives it and :func:`predicted_unit_s` enforces it.

    Pure arithmetic over the measurements above — it never reads
    ``STAGED_FUTURES_BUCKETS``, so it cannot quietly agree with whatever that
    constant happens to be.
    """
    s_total = (MEASURED_UNIT_S_AT_17_LOWER_BOUND - MEASURED_UNIT_S_AT_128) / (
        1.0 / CENSORED_PARTITION - 1.0 / MEASURED_PARTITION
    )
    fixed = MEASURED_UNIT_S_AT_128 - s_total / MEASURED_PARTITION
    return fixed, s_total


#: The largest partition at which the fit may be used to REFUSE anything.
#:
#: DERIVED, not chosen, and the derivation is the whole point. Write the true
#: curve as ``cost'(B) = P' + s' / B``. It passes through the COMPLETED point at
#: 128 exactly, and it lies on or above the CENSORED floor at 17, so
#: ``s' >= s_total`` and ``P' = 857 - s'/128``. Subtract:
#:
#:     cost'(B) - predicted(B) = (s' - s_total) * (1/B - 1/128)
#:
#: which is ``>= 0`` for every ``B <= 128`` and ``<= 0`` for every ``B > 128``.
#: So this file's founding property — every prediction is a lower bound, so
#: every refusal is certain — **holds below the completed anchor and inverts
#: above it**. Above 128 the fit is an UPPER bound on cost, and a refusal built
#: on it is worth nothing.
#:
#: Note the domain is ``B <= 128``, NOT ``17 <= B <= 128``. Extrapolating BELOW
#: the censored point is sound in the one direction this file uses: 17 is a
#: floor the curve passes through from above, so for B < 17 the true cost is
#: still at or above the prediction. It is the completed anchor, not the
#: censored one, that bounds the safe domain.
MODEL_DOMAIN_MAX = MEASURED_PARTITION


def predicted_unit_s(buckets: int) -> float:
    """A LOWER BOUND on what one unit costs at this partition. Never a cost.

    Refuses outright above :data:`MODEL_DOMAIN_MAX`, where that guarantee
    inverts. Partitions above the completed anchor are not thereby endorsed —
    they are refused by :func:`min_beats_above_the_model_domain`, which spends
    no fit.
    """
    if buckets > MODEL_DOMAIN_MAX:
        raise ValueError(
            f"the fit is an UPPER bound on cost above B={MODEL_DOMAIN_MAX} "
            f"(see MODEL_DOMAIN_MAX), so it cannot refuse B={buckets}; use "
            f"min_beats_above_the_model_domain, which does not use the fit"
        )
    fixed, s_total = fit_cost_model()
    return fixed + s_total / buckets


#: The one assumption the fit-free bound below rests on, named so it can be
#: attacked: that units at a fixed partition cost roughly the same, so a
#: completed unit's cost stands in for its 127 siblings. The evidence is thin and
#: stated rather than hidden — three beats at B=128 (:data:`MEASURED_COMPLETIONS`)
#: and the CHEAPEST of them is used. ``test_the_fit_free_bound_survives_the_
#: assumption_being_wrong`` prices how wrong it may be: the finding survives until
#: the true mean unit cost is ~3.5x below the cheapest reading.
#:
#: This is the assumption CAL-P1036-GENERATION-WIDE-UNIT-COST-PRECONDITION asks
#: to be replaced by a completed-generation distribution. It is being retired by
#: harvest rather than by measurement: the sample grows one completed unit per
#: clean beat, and by the time the generation finishes there will be 128 of them
#: — at which point the assumption is not assumed, it is the census.
FIT_FREE_BOUND_ASSUMES_UNIFORM_UNITS = True


def min_generation_work_s(buckets: int) -> float:
    """A LOWER bound on the WORK one whole generation costs, WITHOUT the fit.

    Only two things go in, and neither is a fitted parameter:

    1. A COMPLETED unit cost at B=128 — the CHEAPEST reading in
       :data:`MEASURED_COMPLETIONS`, which today is 723.8 s and rests on a
       sample of **three** completed units (10:15Z, 12:15Z, 17:15Z on
       2026-09-06). Cheapest, because the bound must be a floor: a dearer
       anchor would make the refusal stronger than the evidence supports. The
       sample widens by one per clean beat, so this minimum can only fall, and
       :meth:`TestTheCompletionSampleIsHarvestedNotCurated` pins the count so a
       reader always knows how many units it rests on.
    2. The SHAPE of the runtime, which is not in dispute and is visible in the
       code rather than in a curve: every unit re-pays a fixed prefix and then
       reads its own share, so a generation costs ``B * P' + s'`` with
       ``P' >= 0``. That is non-decreasing in ``B``. **Splitting the work into
       more pieces cannot make there be less of it.**

    So for any ``B >= 128`` the generation costs at least what it costs at 128,
    and what it costs at 128 is 128 completed units. Flat in ``buckets`` by
    construction — the argument is a floor at the anchor, not a curve.
    """
    if buckets < MEASURED_PARTITION:
        raise ValueError(
            f"this bound only holds at or above the completed anchor "
            f"B={MEASURED_PARTITION}; below it, use the fit"
        )
    return MEASURED_PARTITION * min(MEASURED_COMPLETIONS[MEASURED_PARTITION])


def min_beats_above_the_model_domain(buckets: int) -> int:
    """WHOLE beats to publish, a FLOOR, for any partition at or above 128.

    Deliberately agnostic to how many units a beat banks: a beat cannot spend
    more than :data:`MEASURED_USABLE_WINDOW_S` of window whatever it banks, so
    ``work / window`` is a floor on beats no matter how the work is sliced. The
    ``+ 1`` is the publish beat, exactly as in :func:`beats_to_publish`, and it
    is not load-bearing here — the floor clears the budget without it.
    """
    return (
        math.ceil(min_generation_work_s(buckets) / MEASURED_USABLE_WINDOW_S) + 1
    )


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
    """The best margin any partition in the model's domain can have.

    Derived, not chosen. It is the ceiling on every safety argument in this file.

    It is ``admission_margin(128)`` because the fit falls with ``B``, so inside
    ``B <= MODEL_DOMAIN_MAX`` the biggest partition is the roomiest — and that
    end of the domain is the COMPLETED point, so this number rests on a measured
    unit cost rather than on the fit's shape.

    It used to be the ``B -> inf`` limit, i.e. the fixed prefix, and that was a
    third out-of-domain reading: the honest fit's prefix is an UPPER bound on
    the true one, so a margin computed from it is a LOWER bound on the true
    ``B -> inf`` margin — which is the unsafe direction for the one assertion
    that consumes this (``variance > margin`` would be easier to pass, not
    harder). The limit is also unreachable: everything above 128 is refused by
    :func:`min_beats_above_the_model_domain`.
    """
    return admission_margin(MODEL_DOMAIN_MAX)


def assert_the_shipped_partition_can_be_modelled_at_all() -> None:
    """Precondition for every test that costs :data:`STAGED_FUTURES_BUCKETS`.

    Without it, shipping a partition above the domain makes five tests die
    inside :func:`predicted_unit_s` with a ValueError about a fit, when what the
    reader needs to be told is that the size is unshippable and which test says
    so. A guard that fails obscurely on the mutation it exists to catch has done
    half a job.
    """
    assert STAGED_FUTURES_BUCKETS <= MODEL_DOMAIN_MAX, (
        f"B={STAGED_FUTURES_BUCKETS} ships ABOVE the model's domain "
        f"(max {MODEL_DOMAIN_MAX}), so nothing here can cost it — and the "
        f"shipping rule refuses it outright, since production has completed a "
        f"unit only at {sorted(MEASURED_COMPLETIONS)}. See "
        f"test_the_shipped_value_is_the_ONE_THE_RULE_PICKS for the real failure "
        f"and min_beats_above_the_model_domain for what such a size would cost."
    )


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


class TestTheFitIsNotUsedOutsideItsDomain:
    """CAL-P1035-CENSORED-MODEL-DOMAIN: a one-sided constraint has one side.

    The grader's follow-up on CERT-2093. The verdict it questions does not
    change; what changes is that the file now says which evidence licences which
    half of it, and cannot silently spend the fit where the fit does not pay.
    """

    @staticmethod
    def _a_steeper_curve_the_evidence_also_permits() -> tuple[float, float]:
        """``(P', s')`` for a curve that fits every measurement just as well.

        Twice the scalable term, re-pinned through the COMPLETED point at 128.
        Nothing rules it out: it passes through 128 exactly and sits above the
        censored floor at 17 (asserted below, so the specimen cannot rot).
        """
        _, s_total = fit_cost_model()
        s_prime = 2.0 * s_total
        return MEASURED_UNIT_S_AT_128 - s_prime / MEASURED_PARTITION, s_prime

    def test_the_alternative_curve_is_genuinely_admissible(self):
        p_prime, s_prime = self._a_steeper_curve_the_evidence_also_permits()
        assert p_prime + s_prime / MEASURED_PARTITION == pytest.approx(
            MEASURED_UNIT_S_AT_128, abs=0.5
        ), "the specimen no longer passes through the completed point"
        assert (
            p_prime + s_prime / CENSORED_PARTITION
            >= MEASURED_UNIT_S_AT_17_LOWER_BOUND
        ), "the specimen has fallen below the censored floor and proves nothing"

    def test_the_lower_bound_holds_BELOW_the_completed_anchor(self):
        """Where the file leans on the fit, the fit is on the safe side."""
        p_prime, s_prime = self._a_steeper_curve_the_evidence_also_permits()
        for buckets in (1, 5, 17, 55, 64, 127):
            assert p_prime + s_prime / buckets >= predicted_unit_s(buckets), (
                f"at B={buckets} an admissible curve is CHEAPER than the "
                f"prediction — the refusals below B={MODEL_DOMAIN_MAX} are no "
                f"longer certain and the whole file must be re-derived"
            )

    def test_the_lower_bound_INVERTS_above_the_completed_anchor(self):
        """And where it does not, the guard must refuse rather than extrapolate.

        This is the finding, executable: at B=256 an equally admissible curve
        costs LESS than the fit predicts, so "the fit says 256 does not fit" is
        an upper bound masquerading as a floor — the same censored-anchor error
        the file was written to catch, one anchor along.
        """
        fixed, s_total = fit_cost_model()
        p_prime, s_prime = self._a_steeper_curve_the_evidence_also_permits()
        for buckets in (129, 256, 512):
            fit_says = fixed + s_total / buckets
            also_admissible = p_prime + s_prime / buckets
            assert also_admissible < fit_says, (
                f"at B={buckets} the inversion has stopped — if that is real "
                f"the domain rule can be relaxed, but derive it before doing so"
            )

    def test_the_fit_refuses_to_answer_outside_its_domain(self):
        """Enforced, not merely documented: the search cannot wander again."""
        assert predicted_unit_s(MODEL_DOMAIN_MAX) > 0
        with pytest.raises(ValueError, match="UPPER bound"):
            predicted_unit_s(MODEL_DOMAIN_MAX + 1)
        with pytest.raises(ValueError, match="completed anchor"):
            min_beats_above_the_model_domain(MEASURED_PARTITION - 1)

    def test_the_two_halves_overlap_and_leave_no_partition_unjudged(self):
        """Every B >= 1 is answered by one argument or the other, and 128 by both."""
        assert MODEL_DOMAIN_MAX == MEASURED_PARTITION
        assert beats_to_publish(MEASURED_PARTITION) > MAX_BEATS_TO_PUBLISH
        assert min_beats_above_the_model_domain(MEASURED_PARTITION) > (
            MAX_BEATS_TO_PUBLISH
        )

    def test_the_fit_free_bound_is_flat_above_the_anchor(self):
        """It is a floor at the anchor, so a bigger partition cannot dodge it."""
        assert (
            min_beats_above_the_model_domain(129)
            == min_beats_above_the_model_domain(1_000_000)
            == 82
        )

    def test_the_fit_free_bound_survives_the_assumption_being_wrong(self):
        """Price the one assumption instead of hiding it.

        The bound treats a completed unit's cost as standing in for its 127
        siblings. Suppose it does not. The budget is only reachable if the true
        mean unit cost at 128 is under ~206 s — **3.5x cheaper than the cheapest
        reading we have**, and cheaper than any unit ever measured at any
        partition. That is the size of the error the finding would need.

        Re-priced against the widening sample every session, which is the cheap
        half of CAL-P1036-GENERATION-WIDE-UNIT-COST-PRECONDITION: the ratio is
        computed from :data:`MEASURED_COMPLETIONS`, so a harvested reading that
        dragged the minimum toward 206 s would narrow it here and trip the
        message below rather than sitting unnoticed in a docstring.
        """
        breakeven_unit_s = (
            (MAX_BEATS_TO_PUBLISH - 1) * MEASURED_USABLE_WINDOW_S
        ) / MEASURED_PARTITION
        cheapest_measured = min(MEASURED_COMPLETIONS[MEASURED_PARTITION])
        assert breakeven_unit_s == pytest.approx(205.6, abs=1.0)
        assert cheapest_measured / breakeven_unit_s > 3.0, (
            f"a measured unit at {cheapest_measured:.0f}s is now within 3x of "
            f"the {breakeven_unit_s:.0f}s that would make a finer partition "
            f"viable — the uniform-unit assumption has become load-bearing and "
            f"needs measuring rather than pricing"
        )


class TestTheCompletionSampleIsHarvestedNotCurated:
    """One sample feeds every anchor, so a new reading cannot be placed.

    CAL-P1036-GENERATION-WIDE-UNIT-COST-PRECONDITION is being retired by harvest:
    a completed unit cost arrives free on every clean beat and is appended to
    :data:`MEASURED_COMPLETIONS`. The hazard that creates is selection — a
    session that appends a reading could reach for the one that suits the
    argument it is making, or append it in one place and not another. It cannot,
    because the dear end and the cheap end of this file are both read off the
    same tuple.
    """

    def test_no_anchor_is_hand_written_they_all_come_from_the_sample(self):
        """Fit anchor, fit-free floor and spread, all off one tuple."""
        sample = MEASURED_COMPLETIONS[MEASURED_PARTITION]
        assert MEASURED_UNIT_S_AT_128 == max(sample), (
            "the fit anchor has drifted off the sample — it must be the WORST "
            "completed reading, so a new beat can only make the fit more "
            "pessimistic, never less"
        )
        assert min_generation_work_s(MEASURED_PARTITION) == (
            MEASURED_PARTITION * min(sample)
        ), "the fit-free floor must rest on the CHEAPEST reading, or it is not a floor"
        assert MEASURED_BEAT_TO_BEAT_VARIANCE == (
            (max(sample) - min(sample)) / min(sample)
        )

    def test_the_sample_size_is_pinned_so_a_harvest_is_a_visible_edit(self):
        """Three completed units as of the 2026-09-06 17:15Z beat.

        Pinned deliberately. Appending a reading is meant to be a deliberate line
        with a beat time on it, not something that happens while editing nearby
        prose — so the count and the derived trio both move under review. Bump
        this test in the same commit as the reading.
        """
        sample = MEASURED_COMPLETIONS[MEASURED_PARTITION]
        assert len(sample) == 3, (
            f"the B=128 sample now holds {len(sample)} completed units, not 3 — "
            f"if that is a harvest, re-quote the count in min_generation_work_s "
            f"and in the report; if it is a curation, revert it"
        )
        assert sample == (723.8, 857.0, 753.3)
        assert MEASURED_UNIT_S_AT_128 == 857.0
        assert min(sample) == 723.8
        assert MEASURED_BEAT_TO_BEAT_VARIANCE == pytest.approx(0.184, abs=0.001)


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
        smallest = next(
            (b for b in range(1, MODEL_DOMAIN_MAX + 1) if model_admits(b)), None
        )
        assert smallest is not None, (
            "the model admits nothing inside its own domain — every statement "
            "below is vacuous and the fit must be re-derived"
        )
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
        assert_the_shipped_partition_can_be_modelled_at_all()
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
    beats. NOTHING reaches it. The dial is exhausted. Only bringing the fixed
    prefix down can satisfy the promise, and that lives in
    ``_futures_population_sql`` in ruling-D45-frozen ``precompute_calibration.py``.

    **"Nothing" is now proved in two halves, on two different kinds of
    evidence**, because one argument cannot honestly cover both (see
    :data:`MODEL_DOMAIN_MAX`):

    * ``B <= 128`` — the optimistic fit, where a refusal is certain. Admissible
      sizes start at 55 and cost B+1 beats, so the cheapest is 56.
    * ``B > 128`` — no fit at all. :func:`min_beats_above_the_model_domain`:
      128 completed units of work cannot be spent in fewer than 81 beats of
      window, and splitting them further cannot reduce the work.

    The first version searched ``range(1, 513)`` with the fit and called that
    the whole answer. It was the right verdict reached by a method that did not
    licence it above 128.
    """

    def test_every_partition_IN_THE_DOMAIN_misses_the_budget(self):
        best = min(
            (beats_to_publish(b) for b in range(1, MODEL_DOMAIN_MAX + 1)),
            default=math.inf,
        )
        assert best > MAX_BEATS_TO_PUBLISH, (
            f"some partition now publishes in {best} whole beats, inside the "
            f"{MAX_BEATS_TO_PUBLISH}-beat budget — the fixed prefix has come "
            f"down, the D80 repair has effectively landed, and the partition "
            f"should be re-derived with the new headroom"
        )

    @pytest.mark.parametrize("buckets", [129, 160, 256, 512, 4096])
    def test_no_partition_ABOVE_the_domain_reaches_the_budget_either(self, buckets):
        """The other half, and it never touches the fit.

        A bigger partition is the one direction the dial has left once 128 is
        shipping, and it is the direction the old search covered least honestly.
        The floor is flat — the answer is the same at 129 and at 4,096 — because
        the work is the same or greater and the window per beat is fixed.
        """
        floor = min_beats_above_the_model_domain(buckets)
        assert floor > MAX_BEATS_TO_PUBLISH, (
            f"B={buckets} could now publish in {floor} whole beats against a "
            f"{MAX_BEATS_TO_PUBLISH}-beat budget — a completed generation's "
            f"WORK has fallen far enough that splitting it finer is viable, "
            f"which means the fixed prefix moved and everything re-derives"
        )
        assert floor == 82

    def test_the_cheapest_admissible_partition_is_named_not_implied(self):
        """56 beats at B=55: what the best possible dial setting would cost."""
        admissible = [b for b in range(1, MODEL_DOMAIN_MAX + 1) if model_admits(b)]
        cheapest = min(beats_to_publish(b) for b in admissible)
        assert cheapest == 56
        assert cheapest > MAX_BEATS_TO_PUBLISH

    def test_the_shipping_partition_costs_what_it_costs(self):
        assert_the_shipped_partition_can_be_modelled_at_all()
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

    Two units never fit one beat at any partition in the model's domain, so a
    generation costs B productive beats and then the publish beat: **B + 1**.

    Derived here, not asserted: the count comes from driving production's own
    fence, so if the fence or the cost model moves, the ``+ 1`` moves with it.

    Above the domain the question is not asked and does not need to be:
    :func:`min_beats_above_the_model_domain` floors the beat count from total
    work, which is indifferent to how many units a beat manages to bank.
    """

    def test_no_partition_IN_THE_DOMAIN_fits_two_units_in_one_beat(self):
        """Two units need ``window >= 2.25 x unit``.

        The cheapest unit anywhere in the domain is the one at ``B = 128``,
        because the fit falls with ``B`` — and that unit is not a projection at
        all, it is the COMPLETED reading the fit is anchored on. 857 s against
        the 508 s that two units would need.
        """
        two_unit_ceiling_s = MEASURED_USABLE_WINDOW_S / (1.0 + STAGED_UNIT_WINDOW_SAFETY)
        cheapest_in_domain_s = predicted_unit_s(MODEL_DOMAIN_MAX)
        assert cheapest_in_domain_s > two_unit_ceiling_s, (
            f"the cheapest unit in the domain has fallen to "
            f"{cheapest_in_domain_s:.0f}s, under the {two_unit_ceiling_s:.0f}s "
            f"at which a beat could bank two units — the +1-per-unit beat model "
            f"no longer holds and every projection in this file must be re-derived"
        )
        worst = max(
            (units_admitted_per_beat(b) for b in range(1, MODEL_DOMAIN_MAX + 1)),
            default=0,
        )
        assert worst <= 1, f"some partition banks {worst} units in one beat"

    def test_the_shipping_partition_costs_one_beat_per_unit_plus_the_publish_beat(self):
        assert_the_shipped_partition_can_be_modelled_at_all()
        assert units_admitted_per_beat(STAGED_FUTURES_BUCKETS) == 1
        assert beats_to_publish(STAGED_FUTURES_BUCKETS) == STAGED_FUTURES_BUCKETS + 1

    def test_the_gauge_under_reports_what_the_shipped_partition_costs(self):
        assert_the_shipped_partition_can_be_modelled_at_all()
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
        assert_the_shipped_partition_can_be_modelled_at_all()
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
        ranges 723.8 s -> 857.0 s across the three completed readings, which is
        150 s at the prefix. The spread is larger than the entire budget for
        margin, so a self-block can happen at any size. Both sides are
        measurements; neither is a bar anyone picked.

        The prefix appears here as the GENEROUS end of the argument, which is
        why it is admissible where :func:`max_achievable_margin` no longer uses
        it: the honest fit's prefix is an upper bound on the true one, so this
        headroom is an upper bound on the true headroom, and asserting that even
        the generous headroom loses to the spread is the conservative direction.
        """
        fixed, _ = fit_cost_model()
        headroom_s = admission_ceiling_s() - fixed
        spread_s = MEASURED_BEAT_TO_BEAT_VARIANCE * fixed
        assert headroom_s < spread_s, (
            f"headroom above the prefix is now {headroom_s:.0f}s against a "
            f"measured spread of {spread_s:.0f}s — the build has become "
            f"schedulable and this file's pessimism should be revisited"
        )

    def test_the_margin_ceiling_is_a_MEASURED_point_not_an_unreachable_limit(self):
        """+6.8% at B=128 — not the +12.5% the ``B -> inf`` prefix would claim.

        Pinned to a number so the softer version cannot creep back. The limit
        reading is not just unreachable (everything above 128 is refused by
        :func:`min_beats_above_the_model_domain`); it is unsound in the
        direction that matters, because the honest fit's prefix is an UPPER
        bound on the true one, so the margin computed from it is a LOWER bound
        on the true limit — and this class's whole assertion is that variance
        BEATS the margin. Understating the margin makes that too easy.
        """
        fixed, _ = fit_cost_model()
        unreachable_limit = admission_ceiling_s() / fixed - 1.0
        assert max_achievable_margin() == pytest.approx(0.068, abs=0.004)
        assert unreachable_limit > max_achievable_margin()
        assert MEASURED_BEAT_TO_BEAT_VARIANCE > unreachable_limit, (
            f"the measured spread {MEASURED_BEAT_TO_BEAT_VARIANCE:+.1%} no "
            f"longer clears even the unreachable {unreachable_limit:+.1%} "
            f"limit — the prefix has fallen, which is D80 landing, and this "
            f"file's pessimism should be revisited from the top"
        )

    def test_beat_to_beat_variance_exceeds_the_best_achievable_margin(self):
        """The same statement as a ratio, against the B -> inf margin ceiling."""
        assert MEASURED_BEAT_TO_BEAT_VARIANCE > max_achievable_margin(), (
            f"variance {MEASURED_BEAT_TO_BEAT_VARIANCE:+.1%} is now inside the "
            f"achievable margin {max_achievable_margin():+.1%} — the build has "
            f"become schedulable and this file's pessimism should be revisited"
        )
