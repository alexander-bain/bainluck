"""The staged futures partition must be small enough to finish (CAL-P1033, #3536).

THE CLASS OF DEFECT, which is not "128 is the wrong number".

``STAGED_FUTURES_BUCKETS`` carried a *reasoned* sizing argument — units get
cheaper as they get smaller, so a larger count is the safer direction — and that
argument was never checked against a measured unit cost. It was wrong in the one
way that matters: per-unit cost is almost entirely a FIXED prefix, so raising the
bucket count multiplies the total work instead of dividing it. At 128 the build's
own gauge reported ``staged:beats_to_publish`` = 81 and then 95, and
``/api/calibration`` served a 29-hour-old ``generated_at`` while the task ran
every hour. The 12:15Z beat on 2026-09-06 is the clean proof: a deliberate
repo-wide merge freeze bought it a full uninterrupted 1,094 s, it resumed its
cursor without a wipe, it banked ONE unit — and its own ETA got worse.

So the invariant this file pins is not a number. It is:

    **the partition must be small enough that one whole generation publishes
    inside a stated budget of beats, under the cost model production measured** —

and, separately, that a single unit still FITS one beat's usable window, because
a unit that does not fit is refused by the admission fence permanently
(``staged:window_stop:unit_too_large``; see ``_level_self_blocked``). Those two
pull in opposite directions and a partition is only correct between them.

Every constant below is a PRODUCTION MEASUREMENT, not a re-derivation of the
value under test. That is deliberate: a guard whose expected value is recomputed
from the code it guards agrees by construction and proves nothing. If someone
raises the bucket count again, they must first change a measurement here and say
where they measured it.
"""

from __future__ import annotations

import math

import pytest

from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS
from app.tasks.precompute_calibration import (
    STAGED_UNIT_WINDOW_SAFETY,
    _unit_fits_in_window,
)

# --- Production measurements. Source is named for every one. -----------------

#: ``staged:unit_ms_mean`` from the ``calibration:main:phase_ledger`` durable
#: snapshot written at the end of the 2026-09-06 **12:15Z** beat. That beat ran
#: 1,094 s uninterrupted inside a deliberately quiet merge window, resumed its
#: cursor cleanly, and banked its second unit of 128.
#:
#: This is the WORSE of two readings — the 10:15Z beat measured 723.8 s — and
#: the worse one is used deliberately. The fit sizes a partition against a
#: deadline, so an optimistic unit cost buys a unit that does not fit, and a
#: unit that does not fit banks nothing at all.
MEASURED_UNIT_S_AT_128 = 857.0

#: The partition in force when the reading above was taken.
MEASURED_PARTITION = 128

#: The pre-staging monolith over the whole ~110K-market roster: one statement,
#: no banking. Recorded in this module's own history (the 300E rollback notes)
#: and again on #2052, where the same statement was cancelled by Postgres at
#: 1,351,525 ms.
MEASURED_MONOLITH_S = 1350.0

#: ``staged:unit_ms_mean`` (857.0 s) + ``staged:window_left_ms`` (287.2 s) off
#: the same ledger: what one beat actually had to spend after its fixed setup —
#: which includes the ~220 s ``read:futures_generation`` freeze it pays first.
MEASURED_USABLE_WINDOW_S = 1144.2

# --- The budget. These are the ruling, not a measurement. --------------------

#: Beats to publish one generation, counted the way the runtime counts them:
#: whole beats, including the following publish beat (see :func:`beats_to_publish`).
#:
#: 8 → 16 by CERT-2071's repair, 16 → 24 by CERT-2074's follow-up
#: ``CAL-P1033-WHOLE-UNIT-PUBLISH-BUDGET``. The first raise was because the real
#: admission gate leaves so little headroom (see :func:`admission_ceiling_s`)
#: that every partition fast enough for 8 beats has an admission margin under
#: 1%, which is not a margin. The second is because 16 was being compared
#: against a FRACTIONAL projection (13.1 at B=17) that the runtime cannot
#: deliver: one unit per beat is the measured reality at every partition, so
#: B=17 costs 18 whole beats and the assertion was quietly false. 24 is "within
#: a day of productive beats" — the freshness promise the ship is written
#: against.
#:
#: WALL CLOCK WILL EXCEED THIS AND THAT IS NOT A BUG IN THE BUDGET. Self-blocked
#: beats are structural (see :class:`TestNoPartitionIsComfortable`) and every
#: master merge restarts ``worker-heavy`` mid-beat, so 18 productive beats are
#: spread over more than 18 hours. This bounds the WORK a generation costs, not
#: the clock it costs it on. 95.9 was the number that made the page 29 hours
#: stale.
MAX_BEATS_TO_PUBLISH = 24

#: THE ADMISSION CEILING IS NOT OURS TO PICK (CERT-2071's repair). It is
#: ``_unit_fits_in_window``: ``remaining_ms >= reference * STAGED_UNIT_WINDOW_SAFETY``.
#: At the start of a beat ``remaining_ms`` is the whole unit budget and the
#: reference is the previous beat's measured mean, so a partition is viable iff
#: ``cost(B) * STAGED_UNIT_WINDOW_SAFETY <= MEASURED_USABLE_WINDOW_S``.
#:
#: This file first wrote ``MAX_WINDOW_FRACTION = 0.85`` here, by hand. The
#: production rule is 1/1.25 = 0.80, and the 5 percentage points of difference
#: are exactly the ones that let B=5 through a guard the real gate refuses. The
#: factor is now IMPORTED, so it cannot drift from the code it models.
def admission_ceiling_s() -> float:
    return MEASURED_USABLE_WINDOW_S / STAGED_UNIT_WINDOW_SAFETY


#: The measured beat-to-beat spread of ONE unit at a FIXED partition: 723.8 s
#: (10:15Z) then 857.0 s (12:15Z), both at 128. +18.4%.
MEASURED_BEAT_TO_BEAT_VARIANCE = (857.0 - 723.8) / 723.8


def fit_cost_model() -> tuple[float, float]:
    """``(fixed_prefix_s, scalable_total_s)`` from the two measured points.

    ``cost(B) = P + s_total / B``. Two points determine it. Pure arithmetic over
    the measurements above — it never reads ``STAGED_FUTURES_BUCKETS``, so it
    cannot quietly agree with whatever that constant happens to be.
    """
    # cost(1) = P + s_total ; cost(128) = P + s_total/128
    s_total = (MEASURED_MONOLITH_S - MEASURED_UNIT_S_AT_128) / (
        1.0 - 1.0 / MEASURED_PARTITION
    )
    fixed = MEASURED_MONOLITH_S - s_total
    return fixed, s_total


def predicted_unit_s(buckets: int) -> float:
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
    :class:`TestTwoConsecutiveBeatsEachBankAUnit`'s subject and is not repeated
    here.

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
    says ``-1`` for the same case, and for the same reason).
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
    reading of 95 can be checked against — see
    :meth:`TestTheGuardFiresOnTheCodeThatShipped.test_the_historical_value_projects_the_number_production_reported`.
    It is NOT the budget: compare it with :func:`beats_to_publish` and the gap
    is the defect CERT-2074 named.
    """
    return predicted_generation_s(buckets) / MEASURED_USABLE_WINDOW_S


def admission_margin(buckets: int) -> float:
    """How far a partition sits under the production gate, as a fraction.

    Negative means the gate refuses the next beat's first unit. This is also
    the fraction by which the true unit cost may exceed the model before that
    happens, which is the number that matters when the model is a two-point fit.
    """
    return admission_ceiling_s() / predicted_unit_s(buckets) - 1.0


def max_achievable_margin() -> float:
    """The best any partition can do — the B → ∞ limit, i.e. the fixed prefix.

    Derived, not chosen. It is the ceiling on every safety argument in this
    file, and it is small (see the variance test below).
    """
    fixed, _ = fit_cost_model()
    return admission_ceiling_s() / fixed - 1.0


class TestTheFitIsTheOneProductionMeasured:
    """The model has to reproduce its own inputs, or it is not a fit."""

    def test_reproduces_both_measured_points(self):
        assert predicted_unit_s(1) == pytest.approx(MEASURED_MONOLITH_S, abs=0.5)
        assert predicted_unit_s(MEASURED_PARTITION) == pytest.approx(
            MEASURED_UNIT_S_AT_128, abs=0.5
        )

    def test_cost_is_dominated_by_the_fixed_prefix(self):
        """The finding itself, stated as an assertion.

        If this ever fails, the whole sizing argument in this file is void and
        the constant should be re-derived from scratch — because a scalable-cost
        world is the one the ORIGINAL "larger is safer" reasoning assumed, and
        in that world it was right.
        """
        fixed, s_total = fit_cost_model()
        assert fixed > s_total, (
            f"fixed prefix {fixed:.0f}s no longer dominates the scalable part "
            f"{s_total:.0f}s — re-open #3536 before trusting this file"
        )


class TestThePartitionInForcePublishes:
    """Both halves of the invariant, against the constant that actually ships."""

    def test_a_generation_publishes_within_the_beat_budget(self):
        beats = beats_to_publish(STAGED_FUTURES_BUCKETS)
        assert beats <= MAX_BEATS_TO_PUBLISH, (
            f"STAGED_FUTURES_BUCKETS={STAGED_FUTURES_BUCKETS} needs {beats} whole "
            f"beats to publish one generation "
            f"({units_admitted_per_beat(STAGED_FUTURES_BUCKETS)} unit(s) per beat "
            f"plus the publish beat), budget is {MAX_BEATS_TO_PUBLISH}"
        )

    def test_one_unit_still_fits_one_beat(self):
        unit_s = predicted_unit_s(STAGED_FUTURES_BUCKETS)
        ceiling = admission_ceiling_s()
        assert unit_s <= ceiling, (
            f"a unit at {STAGED_FUTURES_BUCKETS} buckets costs {unit_s:.0f}s "
            f"against the production gate's {ceiling:.0f}s ceiling — the fence "
            f"will refuse the next beat's FIRST unit and the build alternates "
            f"between progress and self-blocked beats"
        )

    def test_the_shipped_value_is_the_ONE_THE_RULE_PICKS(self):
        """The choice is searched, not asserted — that is what caught 5 and 6.

        THE RULE. Take the smallest partition whose admission margin reaches
        HALF the maximum margin any partition can reach, subject to the beat
        budget. Every term is derived:

        * the margin is against the production gate, not a chosen fraction;
        * "half the maximum" is a bar computed from the fit, not picked — it
          says "do not sit in the bottom half of the achievable range", which is
          a statement about the shape of the cost curve rather than a taste;
        * smallest-that-qualifies, because publishing sooner is the whole point
          and margin past the bar is bought with beats.

        Under the fit in force it lands on 17 (+3.74% against a +7.30% ceiling).
        B=8 is the first partition that ADMITS AT ALL, at +0.01%. The margin bar
        binds from below at B >= 17 and the beat budget from above at B <= 23,
        so 17 is the smallest of a narrow qualifying band — and it stayed 17
        when CERT-2074's follow-up made the budget count whole beats, because
        the bar it is picked BY is the margin one.
        """
        margin_ceiling = max_achievable_margin()

        def qualifies(b: int) -> bool:
            return (
                admission_margin(b) >= 0.5 * margin_ceiling
                and beats_to_publish(b) <= MAX_BEATS_TO_PUBLISH
            )

        picked = next(
            (b for b in range(1, MEASURED_PARTITION + 1) if qualifies(b)), None
        )
        assert picked is not None, (
            "no partition satisfies the rule — the fixed prefix has grown past "
            "what any partition can absorb; this is the #3536 repair, not a dial"
        )
        assert STAGED_FUTURES_BUCKETS == picked, (
            f"the rule picks {picked} (margin {admission_margin(picked):+.2%}), "
            f"but {STAGED_FUTURES_BUCKETS} ships "
            f"(margin {admission_margin(STAGED_FUTURES_BUCKETS):+.2%})"
        )

    def test_the_partition_is_a_usable_count(self):
        assert isinstance(STAGED_FUTURES_BUCKETS, int)
        assert STAGED_FUTURES_BUCKETS >= 1


class TestTheGuardFiresOnTheCodeThatShipped:
    """A guard that cannot fail the historical value is not a guard.

    #3536 was live for weeks with 128 in the tree. If this file had existed then,
    it had to go red. Asserting that here is the only way to know the predicate
    is load-bearing rather than trivially satisfied by whatever is checked in.
    """

    @pytest.mark.parametrize("buckets", [128, 64, 32, 24])
    def test_the_budget_rejects_every_partition_that_was_too_large(self, buckets):
        # 16 came off this list when CERT-2071's repair raised the budget: at 17
        # whole beats it is inside it, and what rejects it is the SELECTION
        # RULE's margin bar, not the budget. The two bounds reject different
        # things on purpose and neither is redundant. 24 is the tightest member
        # here — 25 whole beats against a budget of 24 — and it is kept for
        # exactly that reason.
        beats = beats_to_publish(buckets)
        assert beats > MAX_BEATS_TO_PUBLISH, (
            f"{buckets} buckets costs {beats} whole beats, which the budget "
            f"would ACCEPT — the budget has been loosened past the bug it exists "
            f"to catch"
        )

    def test_the_historical_value_projects_the_number_production_reported(self):
        """128 → ~95 beats, which is the gauge production actually wrote.

        The independent check on the whole model: ``staged:beats_to_publish``
        was read off the live 12:15Z ledger as **95** with 2 of 128 units
        banked, and the fit was built from a unit cost and a window, never from
        that gauge. (The 10:15Z pair was 724 s → 81, and the model reproduces
        that one too when fed 724.)

        This is the ONE place :func:`gauge_projected_beats` belongs, because the
        thing being reproduced is production's gauge and the gauge is
        fractional. Reality at 128 is 129 whole beats, and the 34-beat gap
        between the two is not rounding — it is the gauge crediting a beat with
        1.3 units of progress it cannot bank.
        """
        beats = gauge_projected_beats(128)
        assert 90 <= beats <= 101, f"model projects {beats:.0f} beats, ledger said 95"

    def test_the_window_ceiling_rejects_a_partition_that_would_deadlock(self):
        """The other direction: too FEW buckets is its own failure mode.

        B=1 is the monolith — one 1,350 s unit against a 1,141 s window. It never
        completes, banks nothing, and is the state #2052 recorded as a Postgres
        statement timeout.

        The gauge would happily accept it at 1.18 beats, which is what made this
        test necessary. Counting whole beats (CERT-2074) catches it too — a beat
        banking nothing is ``inf`` — so the two now agree, and the ceiling
        assertion is kept because it says WHY in one line instead of leaving a
        reader to infer it from an infinity.
        """
        ceiling = admission_ceiling_s()
        assert predicted_unit_s(1) > ceiling
        assert gauge_projected_beats(1) <= MAX_BEATS_TO_PUBLISH
        assert beats_to_publish(1) == math.inf

class TestABeatBanksAtMostOneUnit:
    """CERT-2074's follow-up: the budget counts WHOLE beats, because runtime does.

    ``CAL-P1033-WHOLE-UNIT-PUBLISH-BUDGET``. Every projection in this file's
    first two presentations was fractional — 13.1 beats at B=17 — and the
    runtime cannot spend 0.1 of a beat. Two units never fit one beat at ANY
    partition, so a generation costs B productive beats and then the publish
    beat: **B + 1**, which at B=17 is 18 against a budget the file asserted as
    16. The number under test did not move; the arithmetic under it was false,
    and a false projection whose next honest correction fires the search's
    ``"no partition satisfies the rule"`` arm is a landmine for the next reader.

    Derived here, not asserted: the count comes from driving production's own
    fence, so if the fence or the cost model moves, the ``+ 1`` moves with it.
    """

    def test_no_partition_ever_fits_two_units_in_one_beat(self):
        """The structural fact the whole-beat budget rests on.

        Two units need ``window >= 2.25 x unit`` (spend one, then clear the
        1.25x fence with what is left). Even the B → ∞ floor on unit cost — the
        fixed prefix, which no partition can go below — is far above the
        ``window / 2.25`` that would allow it.
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
        """The defect itself, pinned so nobody re-reads the gauge as a budget.

        This is also the guard firing on the code that shipped: at B=17 the
        honest cost is 18 whole beats, which the pre-repair budget of 16 would
        have REJECTED — the assertion passed only because it was comparing
        against 13.1.
        """
        gauge = gauge_projected_beats(STAGED_FUTURES_BUCKETS)
        real = beats_to_publish(STAGED_FUTURES_BUCKETS)
        assert gauge < real, (
            "the gauge no longer under-reports — production's projection has "
            "been made whole-unit and this file should read it directly"
        )
        assert real > 16, (
            "the honest cost now fits the pre-CERT-2074 budget of 16; the "
            "follow-up's premise has expired and the budget should come back down"
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
    its inequality. A guard that re-derives the rule it is checking agrees by
    construction; this one can only pass if the shipped code says so.
    """

    @staticmethod
    def _two_beats(buckets: int, carried_level_s: float) -> tuple[bool, bool]:
        """``(beat 1 admitted, beat 2 admitted)`` at a partition.

        Beat 1 opens with the level carried from the PREVIOUS partition's beats
        (nothing at this size has run yet) and, if it is admitted, ends having
        measured this size's own cost. Beat 2 opens on that new level. That
        second opening is the one the BLOCK caught.
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

    @pytest.mark.parametrize("buckets", [2, 4, 5, 6, 7])
    def test_it_fails_on_beat_two_for_every_partition_the_block_named(self, buckets):
        """The falsifier, run against the values this guard must reject.

        5 is the one CERT-2071 caught on the exact SHA. Each of these is
        admitted on beat one — the carried 128-era level is small enough to let
        it through — and refused on beat two by its own measurement. That
        asymmetry is precisely why a one-beat check could not see the defect,
        and why this class exists.
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
    margin" cannot be fully satisfied by a dial, and the reason the frozen-file
    repair is required rather than optional. Anyone who reads a self-blocked
    beat as evidence against the shipped partition should meet this first.
    """

    def test_the_fixed_prefix_alone_nearly_fills_the_window(self):
        fixed, _ = fit_cost_model()
        share = fixed * STAGED_UNIT_WINDOW_SAFETY / MEASURED_USABLE_WINDOW_S
        assert share > 0.9, (
            f"the fixed prefix at the safety factor is {share:.1%} of the unit "
            f"budget — if this has fallen below 90% the repair has landed and "
            f"the partition should be re-derived with the new headroom"
        )

    def test_the_best_margin_any_partition_can_reach_is_small(self):
        assert max_achievable_margin() < 0.10, (
            "more than 10% headroom is now reachable — re-derive the partition"
        )

    def test_beat_to_beat_variance_exceeds_the_best_achievable_margin(self):
        """The structural statement: self-blocked beats are not a partition bug.

        One unit measured 723.8 s and then 857.0 s on consecutive beats at the
        SAME partition — +18.4%, against a best-case margin of +7.3%. No value
        of ``STAGED_FUTURES_BUCKETS`` can absorb that, including the 128 that
        shipped for weeks. The dial changes how often a self-block costs
        something, never whether one can happen.
        """
        assert MEASURED_BEAT_TO_BEAT_VARIANCE > max_achievable_margin(), (
            f"variance {MEASURED_BEAT_TO_BEAT_VARIANCE:+.1%} is now inside the "
            f"achievable margin {max_achievable_margin():+.1%} — the build has "
            f"become schedulable and this file's pessimism should be revisited"
        )
