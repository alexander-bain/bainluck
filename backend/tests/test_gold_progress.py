"""The gold-set progress meter, and the streak that is its real leg (UX-P117).

── EVERY ANCHOR HERE IS A LITERAL, WHICH IS THE POINT (gotcha #44) ──────────────

``current_streak`` takes ``today`` as an argument for exactly this reason: the
computation has real edge cases (a streak alive from yesterday, a one-day gap, a
future-dated row) and none of them should be settled against a live wall clock. A
test that seeds days relative to ``date.today()`` is a test that goes red on a
schedule — that is the fourth-instance history behind gotcha #44, and the remedy
it names is to freeze the clock out when the fixture carries dates of its own.

So there is no ``date.today()`` in this file and no ``if`` in any anchor.
"""

from __future__ import annotations

from datetime import date

from app.utils.gold_progress import (
    GOLD_DAILY_TARGET,
    GOLD_TOTAL_TARGET,
    current_streak,
    gold_progress,
    gold_spread_target,
)

TODAY = date(2026, 8, 21)


class TestStreak:
    def test_no_days_is_zero(self):
        assert current_streak([], today=TODAY) == 0

    def test_today_alone_is_one(self):
        assert current_streak(["2026-08-21"], today=TODAY) == 1

    def test_consecutive_run_ending_today(self):
        days = ["2026-08-19", "2026-08-20", "2026-08-21"]
        assert current_streak(days, today=TODAY) == 3

    def test_a_streak_that_ran_through_last_night_is_still_alive(self):
        """9am on a day he has not started yet must not read zero.

        The first thing a person does with a counter that lies is stop reading it.
        """
        days = ["2026-08-19", "2026-08-20"]
        assert current_streak(days, today=TODAY) == 2

    def test_a_two_day_gap_breaks_it(self):
        days = ["2026-08-18", "2026-08-19"]
        assert current_streak(days, today=TODAY) == 0

    def test_only_the_run_touching_today_counts(self):
        """An old five-day run does not resurrect a broken streak."""
        days = [
            "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05",
            "2026-08-21",
        ]
        assert current_streak(days, today=TODAY) == 1

    def test_month_boundary(self):
        days = ["2026-07-31", "2026-08-01"]
        assert current_streak(days, today=date(2026, 8, 1)) == 2

    def test_a_future_dated_day_is_ignored_not_counted(self):
        """A clock-skewed client can post one; neither crash nor award a streak."""
        days = ["2026-08-25", "2026-08-21"]
        assert current_streak(days, today=TODAY) == 1

    def test_a_future_dated_day_alone_is_zero(self):
        assert current_streak(["2026-08-25"], today=TODAY) == 0

    def test_duplicate_days_do_not_inflate(self):
        days = ["2026-08-21", "2026-08-21", "2026-08-20"]
        assert current_streak(days, today=TODAY) == 2

    def test_empty_strings_are_dropped(self):
        assert current_streak(["", "2026-08-21"], today=TODAY) == 1


class TestSpreadTarget:
    def test_it_is_derived_from_the_two_targets(self):
        assert gold_spread_target(250, 20) == 13

    def test_it_rounds_up(self):
        """12.5 days at pace is 13 days of work, never 12."""
        assert gold_spread_target(250, 20) == 13
        assert gold_spread_target(100, 30) == 4

    def test_defaults_match_alexs_figures(self):
        assert GOLD_DAILY_TARGET == 20
        assert GOLD_TOTAL_TARGET == 250
        assert gold_spread_target() == 13

    def test_a_zero_daily_target_does_not_divide_by_zero(self):
        assert gold_spread_target(250, 0) == 0


class TestGoldProgress:
    def test_todays_production_shape(self):
        """The corpus as measured on 2026-08-21, in Pacific days.

        88 rows over 7 days — and the spread leg FAILS at 7 of 13 while the raw
        total (35%) looks like ordinary progress. That divergence is the reason
        the legs are reported separately rather than as one percentage.
        """
        days = [
            "2026-05-24", "2026-05-25", "2026-08-10",
            "2026-08-14", "2026-08-17", "2026-08-19", "2026-08-20",
        ]
        progress = gold_progress(total=88, today_count=0, days=days, today=TODAY)
        assert progress["total"] == 88
        assert progress["total_met"] is False
        assert progress["distinct_days"] == 7
        assert progress["spread_target"] == 13
        assert progress["spread_met"] is False
        # 08-20 is yesterday, so the streak is alive at 2 (08-19 + 08-20).
        assert progress["streak"] == 2
        assert progress["first_day"] == "2026-05-24"
        assert progress["last_day"] == "2026-08-20"

    def test_a_big_corpus_from_few_sittings_fails_the_spread_leg(self):
        """The failure the meter exists to make visible.

        250 labels from three days is the target hit and the REQUIREMENT missed —
        the slate turns over daily, so those are 250 opinions about three slates.
        """
        progress = gold_progress(
            total=250,
            today_count=20,
            days=["2026-08-19", "2026-08-20", "2026-08-21"],
            today=TODAY,
        )
        assert progress["total_met"] is True
        assert progress["daily_met"] is True
        assert progress["spread_met"] is False

    def test_daily_leg_is_met_at_the_target_not_above_it(self):
        assert gold_progress(
            total=1, today_count=20, days=["2026-08-21"], today=TODAY
        )["daily_met"] is True
        assert gold_progress(
            total=1, today_count=19, days=["2026-08-21"], today=TODAY
        )["daily_met"] is False

    def test_an_empty_corpus_reports_zeros_not_none(self):
        progress = gold_progress(total=0, today_count=0, days=[], today=TODAY)
        assert progress["distinct_days"] == 0
        assert progress["streak"] == 0
        assert progress["first_day"] is None
        assert progress["last_day"] is None
        assert progress["spread_met"] is False
