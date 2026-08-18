"""LAT-P069 (#1609, #224) — the `turbo_collapse` pair's budget may not be guessed.

The property under test is ruling 075's, stated twice:

1. A budget derived from measured history may never fall below the phase's own
   measured floor — and when it would, the answer is a **visible refusal** that
   names both numbers, not a clamp and not a silent skip.
2. "Could not measure" renders as could-not-measure, **never as a default
   number.**

The second is the live case as of the day this file was written. Both tasks have
exactly ONE bracketed completion each, taken from LAT-P068's S4 capture of
celery's `active` set. One observation cannot produce a p95 — at n=1 the p95 IS
the max — so no budget is derived, the wired 3600 s is left alone, and the
verdict says so out loud.

These tests are also the guard against the failure mode that would be easiest to
commit here: someone reads "bound the turbo_collapse pair", picks a
plausible-looking smaller number, and ships it. `test_the_wire_matches_the_module`
and `test_no_budget_below_the_measured_floor_survives` are what turn that red.
"""

from __future__ import annotations

import pytest

from app.utils.turbo_collapse_budget import (
    COULD_NOT_MEASURE,
    DERIVED,
    MEASURED_FLOOR_PROVENANCE,
    MEASURED_FLOOR_S,
    MIN_SAMPLES,
    REFUSED_BELOW_FLOOR,
    ROUND_TO_S,
    SAFETY_FACTOR,
    WIRED_SOFT_TIME_LIMIT_S,
    derive_all,
    derive_budget,
    nearest_rank_p95,
)

BOTH = ("turbo_collapse_futures", "turbo_collapse_odds")


class TestTheMeasuredFloor:
    def test_both_tasks_have_a_floor_and_it_carries_its_provenance(self):
        """A hard-coded number with no provenance is folklore (ruling 074)."""
        for task in BOTH:
            assert task in MEASURED_FLOOR_S
            assert MEASURED_FLOOR_S[task] > 0
            prov = MEASURED_FLOOR_PROVENANCE.get(task)
            assert prov, f"{task} floor has no provenance"
            # The provenance must name the instrument and admit the sample size.
            assert "LAT-P068" in prov
            assert "n=1" in prov, "a floor from one observation must say so"

    def test_the_floors_are_the_upper_end_of_the_observed_bracket(self):
        """S4 brackets a completion between the last present and first absent
        sample. The budget-relevant end is the UPPER one: it is a duration we
        watched the task complete at, so killing below it kills normal work."""
        assert MEASURED_FLOOR_S["turbo_collapse_futures"] == pytest.approx(853.8, abs=0.1)
        assert MEASURED_FLOOR_S["turbo_collapse_odds"] == pytest.approx(474.9, abs=0.1)


class TestTheWire:
    def test_the_wire_matches_the_module(self):
        """The decorator and `WIRED_SOFT_TIME_LIMIT_S` must not drift apart.

        Reads the LIVE celery task objects, not the source text, so this cannot
        be satisfied by a comment that happens to contain the right digits.
        """
        from app.tasks import turbo_collapse_futures, turbo_collapse_odds

        live = {
            "turbo_collapse_futures": turbo_collapse_futures,
            "turbo_collapse_odds": turbo_collapse_odds,
        }
        for task, obj in live.items():
            assert obj.soft_time_limit == WIRED_SOFT_TIME_LIMIT_S[task], (
                f"{task}: decorator says {obj.soft_time_limit}, module says "
                f"{WIRED_SOFT_TIME_LIMIT_S[task]}. Change BOTH, and only with a "
                f"measurement behind it."
            )

    def test_the_hard_limit_stays_above_the_soft_limit(self):
        from app.tasks import turbo_collapse_futures, turbo_collapse_odds

        for obj in (turbo_collapse_futures, turbo_collapse_odds):
            assert obj.time_limit > obj.soft_time_limit

    def test_the_wired_budget_is_never_below_the_measured_floor(self):
        """Ruling 075 applied to the wire itself, not just to the derivation."""
        for task in BOTH:
            assert WIRED_SOFT_TIME_LIMIT_S[task] >= MEASURED_FLOOR_S[task], (
                f"{task} is wired to kill runs shorter than a completion we have "
                f"already observed"
            )


class TestCouldNotMeasure:
    def test_one_observation_derives_nothing(self):
        """The live state. n=1 is the whole reason this module exists."""
        d = derive_budget("turbo_collapse_futures", [853_800])
        assert d.verdict == COULD_NOT_MEASURE
        assert d.derived_soft_time_limit_s is None
        assert d.samples_n == 1
        assert d.p95_s is None

    def test_no_history_derives_nothing(self):
        for arg in (None, []):
            d = derive_budget("turbo_collapse_odds", arg)
            assert d.verdict == COULD_NOT_MEASURE
            assert d.derived_soft_time_limit_s is None

    def test_a_refusal_never_carries_a_number_that_reads_as_an_answer(self):
        """The directive's exact words: could-not-measure renders as
        could-not-measure, NEVER as a default number."""
        for task in BOTH:
            d = derive_budget(task, [])
            assert d.derived_soft_time_limit_s is None
            assert not d.actionable

    def test_the_refusal_names_the_floor_and_the_sample_count(self):
        """Ruling 075 property 2 — a refusal that says only 'too small' cannot
        be acted on by the next reader."""
        d = derive_budget("turbo_collapse_futures", [853_800])
        assert d.measured_floor_s == MEASURED_FLOOR_S["turbo_collapse_futures"]
        assert str(MIN_SAMPLES) in d.reason
        assert d.provenance and "LAT-P068" in d.provenance

    def test_the_boundary_is_min_samples_exactly(self):
        below = derive_budget("turbo_collapse_odds", [500_000] * (MIN_SAMPLES - 1))
        at = derive_budget("turbo_collapse_odds", [500_000] * MIN_SAMPLES)
        assert below.verdict == COULD_NOT_MEASURE
        assert at.verdict == DERIVED


class TestTheFloorGuarantee:
    def test_a_derivation_below_the_floor_is_refused_not_clamped(self):
        """Ruling 075: refuse loudly, mark unrunnable, do NOT quietly clamp to
        the floor. A clamp would hide that the history is starved."""
        # 10 s runs x2 safety = 20 s, far below the 853.8 s floor.
        d = derive_budget("turbo_collapse_futures", [10_000] * MIN_SAMPLES)
        assert d.verdict == REFUSED_BELOW_FLOOR
        assert d.derived_soft_time_limit_s is None
        assert "853.8" in d.reason
        assert not d.actionable

    def test_the_refusal_names_both_numbers(self):
        d = derive_budget("turbo_collapse_futures", [10_000] * MIN_SAMPLES)
        assert str(d.measured_floor_s) in d.reason
        # 10 s x2 = 20 s, rounded up to the 60 s granularity. The refusal names the
        # candidate it actually rejected, not the pre-rounding intermediate.
        assert "60s" in d.reason, "the impossible arithmetic must be named too"
        assert "10.0s" in d.reason, "the p95 behind it must be named too"

    def test_no_budget_below_the_measured_floor_survives(self):
        """Swept across a wide range of starved histories: not one produces a
        number under the floor. This is the property, not an example of it."""
        for ms in (1, 100, 1_000, 30_000, 120_000, 300_000, 400_000):
            for task in BOTH:
                d = derive_budget(task, [ms] * MIN_SAMPLES)
                if d.derived_soft_time_limit_s is not None:
                    assert d.derived_soft_time_limit_s >= MEASURED_FLOOR_S[task]


class TestDerivation:
    def test_a_real_derivation_produces_a_rounded_number_above_the_floor(self):
        d = derive_budget("turbo_collapse_futures", [800_000] * 10)
        assert d.verdict == DERIVED
        assert d.p95_s == pytest.approx(800.0)
        # 800 s x2.0 = 1600 s, which is NOT a whole minute, so it rounds UP to 1620.
        assert d.derived_soft_time_limit_s == 1620
        assert d.derived_soft_time_limit_s >= MEASURED_FLOOR_S["turbo_collapse_futures"]
        assert d.actionable, "1600 differs from the wired 3600, so it is actionable"

    def test_budgets_round_up_never_down(self):
        # p95 = 500.5 s -> x2 = 1001 s -> rounds UP to 1020, never down to 960.
        d = derive_budget("turbo_collapse_odds", [500_500] * 10)
        assert d.derived_soft_time_limit_s == 1020
        assert d.derived_soft_time_limit_s % ROUND_TO_S == 0
        assert d.derived_soft_time_limit_s >= 500.5 * SAFETY_FACTOR

    def test_p95_is_nearest_rank_not_interpolated(self):
        """Interpolation invents a duration that was never recorded."""
        sample = [1_000, 2_000, 3_000, 4_000, 5_000]
        assert nearest_rank_p95(sample) == 5.0
        assert nearest_rank_p95([]) is None

    def test_p95_ignores_ordering(self):
        """`recent_durations_ms` arrives newest-first; the percentile sorts."""
        asc = derive_budget("turbo_collapse_odds", [100_000, 200_000, 300_000, 400_000, 500_000])
        desc = derive_budget("turbo_collapse_odds", [500_000, 400_000, 300_000, 200_000, 100_000])
        assert asc.derived_soft_time_limit_s == desc.derived_soft_time_limit_s

    def test_the_safety_factor_is_declared_not_hidden(self):
        """It is the one number here that is chosen rather than measured."""
        assert SAFETY_FACTOR >= 1.0
        d = derive_budget("turbo_collapse_futures", [800_000] * 10)
        assert str(SAFETY_FACTOR) in d.reason


class TestTheAdminSurface:
    def test_derive_all_reports_both_tasks_even_with_no_metrics(self):
        """A task absent from a census and a task with nothing to report are
        different facts (gotcha #53). Neither may be silently dropped."""
        rows = derive_all({})
        assert {r["task"] for r in rows} == set(BOTH)
        for r in rows:
            assert r["verdict"] == COULD_NOT_MEASURE
            assert r["derived_soft_time_limit_s"] is None
            assert r["samples_n"] == 0

    def test_derive_all_survives_a_no_data_payload(self):
        """`get_task_metrics` answers `{"status": "no_data"}` for these two
        today, which has no `recent_durations_ms` key at all."""
        rows = derive_all({t: {"status": "no_data"} for t in BOTH})
        assert all(r["verdict"] == COULD_NOT_MEASURE for r in rows)

    def test_derive_all_handles_none(self):
        assert len(derive_all(None)) == 2

    def test_every_row_carries_the_wired_value_for_comparison(self):
        for r in derive_all({}):
            assert r["wired_soft_time_limit_s"] == WIRED_SOFT_TIME_LIMIT_S[r["task"]]
