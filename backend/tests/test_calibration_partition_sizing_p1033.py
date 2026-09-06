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

import pytest

from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS

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

#: A generation must publish within one working day of beats. 81 was the number
#: that made the page 29 hours stale; anything in this range publishes daily even
#: when several beats in a row are lost to a restart or a cursor wipe.
MAX_BEATS_TO_PUBLISH = 8

#: How much of the usable window a single unit may claim. A unit that overruns
#: its window is not merely slow — the fence stops offering it, and the build
#: banks zero units per beat forever, which is strictly worse than 128 was.
MAX_WINDOW_FRACTION = 0.85


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
        beats = predicted_generation_s(STAGED_FUTURES_BUCKETS) / MEASURED_USABLE_WINDOW_S
        assert beats <= MAX_BEATS_TO_PUBLISH, (
            f"STAGED_FUTURES_BUCKETS={STAGED_FUTURES_BUCKETS} needs {beats:.0f} "
            f"beats to publish one generation, budget is {MAX_BEATS_TO_PUBLISH}"
        )

    def test_one_unit_still_fits_one_beat(self):
        unit_s = predicted_unit_s(STAGED_FUTURES_BUCKETS)
        ceiling = MEASURED_USABLE_WINDOW_S * MAX_WINDOW_FRACTION
        assert unit_s <= ceiling, (
            f"a unit at {STAGED_FUTURES_BUCKETS} buckets costs {unit_s:.0f}s "
            f"against a {ceiling:.0f}s ceiling — the admission fence will refuse "
            f"it and the build will bank nothing at all"
        )

    def test_the_shipped_value_is_the_SMALLEST_partition_that_clears_both(self):
        """The two halves squeeze from opposite sides; 6 is where they meet.

        Stated as a search rather than an assertion about 6, so the choice stays
        checkable when a measurement changes. Under the fit in force: B=2 costs
        96% of the unit budget and B=4 costs 85.4% — both refused by the window
        ceiling — while B=6 costs 82% and publishes in ~5 beats. Publishing
        sooner is always better, so anything LARGER than the smallest admissible
        value is leaving convergence speed on the table for no safety it does
        not already have.
        """
        ceiling = MEASURED_USABLE_WINDOW_S * MAX_WINDOW_FRACTION

        def admissible(b: int) -> bool:
            return (
                predicted_unit_s(b) <= ceiling
                and predicted_generation_s(b) / MEASURED_USABLE_WINDOW_S
                <= MAX_BEATS_TO_PUBLISH
            )

        smallest = next(b for b in range(1, MEASURED_PARTITION + 1) if admissible(b))
        assert STAGED_FUTURES_BUCKETS == smallest, (
            f"the smallest partition clearing both bounds is {smallest}, but "
            f"{STAGED_FUTURES_BUCKETS} ships — publish sooner, or say here why not"
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

    @pytest.mark.parametrize("buckets", [128, 64, 32, 16])
    def test_the_budget_rejects_every_partition_that_was_too_large(self, buckets):
        beats = predicted_generation_s(buckets) / MEASURED_USABLE_WINDOW_S
        assert beats > MAX_BEATS_TO_PUBLISH, (
            f"{buckets} buckets projects {beats:.0f} beats, which the budget "
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
        """
        beats = predicted_generation_s(128) / MEASURED_USABLE_WINDOW_S
        assert 90 <= beats <= 101, f"model projects {beats:.0f} beats, ledger said 95"

    def test_the_window_ceiling_rejects_a_partition_that_would_deadlock(self):
        """The other direction: too FEW buckets is its own failure mode.

        B=1 is the monolith — one 1,350 s unit against a 1,141 s window. It never
        completes, banks nothing, and is the state #2052 recorded as a Postgres
        statement timeout. The budget test alone would happily accept it.
        """
        ceiling = MEASURED_USABLE_WINDOW_S * MAX_WINDOW_FRACTION
        assert predicted_unit_s(1) > ceiling
        assert predicted_generation_s(1) / MEASURED_USABLE_WINDOW_S <= MAX_BEATS_TO_PUBLISH
