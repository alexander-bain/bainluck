"""LAT-P022 (#1609): grading a beat's SCHEDULE ADHERENCE from recorded counters.

The defect these guard against is not a crash, it is a confident wrong answer.
#1609 was filed twice off a queue-depth eyeball because the system could not
answer "is this beat running as often as it is scheduled to?", and the two
plausible ways to answer it from the old payload were both wrong:

* dividing ``successes_24h`` by 24 hours, when the counter's real window was
  about ONE hour (measured 2026-08-09: six fixed-cadence tasks reading 52-63
  presented as missing ~96% of their fires while running at 0.99x cadence); and
* reading ``last_duration_ms`` as the task's runtime, when it is one sample and
  systematically the *cheap* one for a self-gating task.

So the tests below care most about the refusals: unmeasurable must stay
unmeasurable, and a short window must never be allowed to manufacture an alarm.
"""

from datetime import timedelta

import pytest

from app.utils.schedule_adherence import (
    BEHIND_RATIO,
    MIN_EXPECTED_FIRES,
    OVERRUN_RATIO,
    adherence,
    beat_intervals,
    expected_fires,
    find_lapping,
    percentile,
    schedule_interval_s,
)


class _Crontab:
    """Stand-in for celery's crontab: the parsed field sets it exposes."""

    def __init__(self, minute, hour, dow=range(7), dom=range(1, 32),
                 moy=range(1, 13)):
        self.minute = set(minute)
        self.hour = set(hour)
        self.day_of_week = set(dow)
        self.day_of_month = set(dom)
        self.month_of_year = set(moy)


class TestPercentile:
    def test_empty_sample_is_none_not_zero(self):
        # Zero would read as "instant task", which is the opposite of unknown.
        assert percentile([], 0.95) is None

    def test_p95_picks_the_tail_not_the_median(self):
        # Nearest-rank: with 20 samples p95 is the 19th, so a tail that is 10%
        # of runs is caught while the median stays at 10.
        vals = [10] * 18 + [5000] * 2
        assert percentile(vals, 0.95) == 5000
        assert percentile(vals, 0.5) == 10

    def test_a_lone_outlier_in_twenty_does_not_move_p95(self):
        # Deliberate: one slow run in twenty is not a task lapping itself, and a
        # detector that treats it as one flags every task that ever had a bad
        # minute. p100 still sees it if a caller wants that.
        vals = [10] * 19 + [5000]
        assert percentile(vals, 0.95) == 10
        assert percentile(vals, 1.0) == 5000

    def test_single_sample(self):
        assert percentile([42], 0.95) == 42

    def test_ignores_nones(self):
        assert percentile([None, 5, None, 7], 1.0) == 7


class TestScheduleIntervalConversion:
    def test_plain_seconds(self):
        assert schedule_interval_s(180.0) == 180.0

    def test_timedelta(self):
        assert schedule_interval_s(timedelta(minutes=5)) == 300.0

    def test_crontab_every_two_minutes(self):
        cron = _Crontab(minute=range(0, 60, 2), hour=range(24))
        assert schedule_interval_s(cron) == pytest.approx(120.0)

    def test_crontab_hourly_at_a_fixed_minute(self):
        assert schedule_interval_s(_Crontab(minute=[47], hour=range(24))) == 3600.0

    def test_crontab_daily(self):
        assert schedule_interval_s(_Crontab(minute=[10], hour=[7])) == 86400.0

    def test_weekly_crontab_is_not_graded_as_daily(self):
        # A weekly sentinel firing once is on schedule; treating it as daily
        # would report it 86% behind every single day.
        weekly = _Crontab(minute=[10], hour=[7], dow=[1])
        assert schedule_interval_s(weekly) == pytest.approx(86400.0 * 7)

    def test_unrecognised_schedule_is_none_not_a_guess(self):
        assert schedule_interval_s(object()) is None
        assert schedule_interval_s(None) is None

    def test_zero_and_negative_are_none(self):
        assert schedule_interval_s(0) is None
        assert schedule_interval_s(-5) is None

    def test_bool_is_not_read_as_a_number(self):
        # `True` is an int in Python; a schedule of 1 second inferred from a
        # stray boolean would make every task look catastrophically behind.
        assert schedule_interval_s(True) is None


class TestBeatIntervals:
    def test_one_entry(self):
        sched = {"a": {"task": "app.tasks.foo", "schedule": 120.0}}
        assert beat_intervals(sched) == {"app.tasks.foo": 120.0}

    def test_several_entries_for_one_task_combine_reciprocally(self):
        # The statpal-schedules shape: 4 beat entries, one task, one metric
        # label. Its effective cadence is 4x, and taking any single entry's
        # interval would under-count the expectation fourfold.
        sched = {
            f"e{i}": {"task": "app.tasks.sync_statpal_schedules", "schedule": 3600.0}
            for i in range(4)
        }
        assert beat_intervals(sched) == {"app.tasks.sync_statpal_schedules": 900.0}

    def test_unparseable_entry_is_dropped_not_defaulted(self):
        sched = {
            "good": {"task": "app.tasks.foo", "schedule": 60.0},
            "bad": {"task": "app.tasks.bar", "schedule": object()},
        }
        assert beat_intervals(sched) == {"app.tasks.foo": 60.0}

    def test_empty_schedule(self):
        assert beat_intervals({}) == {}
        assert beat_intervals(None) == {}


class TestAdherenceRefusesToGuess:
    """The half that matters most: not grading when grading is not possible."""

    def test_missing_window_is_unmeasurable_not_behind(self):
        # Every counter written before the window stamp existed reads like this.
        # Calling it "behind" would light up the entire health surface RED on
        # deploy for a system that is running perfectly.
        g = adherence(starts=5, starts_window_s=None, interval_s=60)
        assert g["verdict"] == "unmeasurable"
        assert g["reason"] == "no_interval_or_window"
        assert g["ratio"] is None

    def test_missing_interval_is_unmeasurable(self):
        g = adherence(starts=5, starts_window_s=3600, interval_s=None)
        assert g["verdict"] == "unmeasurable"

    def test_window_too_short_for_the_cadence_is_unmeasurable(self):
        # 90 seconds has nothing to say about an hourly beat. Observing zero
        # fires here is the OVERWHELMINGLY likely outcome for a healthy task.
        g = adherence(starts=0, starts_window_s=90, interval_s=3600)
        assert g["verdict"] == "unmeasurable"
        assert "window_too_short" in g["reason"]

    def test_zero_starts_in_a_long_window_IS_graded(self):
        # The contrast case: the same zero, over a window with room for 24
        # fires, is real evidence and must not be refused.
        g = adherence(starts=0, starts_window_s=86400, interval_s=3600)
        assert g["verdict"] == "behind"
        assert g["ratio"] == 0.0

    def test_threshold_boundary_is_measurable(self):
        g = adherence(starts=2, starts_window_s=MIN_EXPECTED_FIRES * 60,
                      interval_s=60)
        assert g["verdict"] != "unmeasurable"


class TestAdherenceVerdicts:
    def test_on_schedule(self):
        g = adherence(starts=59, starts_window_s=3600, interval_s=60)
        assert g["verdict"] == "on_schedule"
        assert g["ratio"] == pytest.approx(0.98, abs=0.02)

    def test_slightly_under_is_still_on_schedule(self):
        # A deploy restart and beat/worker clock alignment cost a fire or two
        # legitimately. A detector that pages at 0.9x gets muted, and a muted
        # detector is worse than none.
        g = adherence(starts=54, starts_window_s=3600, interval_s=60)
        assert g["ratio"] == 0.9
        assert g["verdict"] == "on_schedule"

    def test_well_under_is_behind(self):
        g = adherence(starts=10, starts_window_s=3600, interval_s=60)
        assert g["verdict"] == "behind"
        assert "10 starts against 60.0 scheduled" in g["reason"]

    def test_behind_boundary_matches_the_constant(self):
        window, interval = 3600, 60
        just_over = int(BEHIND_RATIO * (window / interval)) + 1
        assert adherence(starts=just_over, starts_window_s=window,
                         interval_s=interval)["verdict"] == "on_schedule"

    def test_p95_over_interval_is_overruns_even_when_fire_count_looks_fine(self):
        # The CAUSE shape, and why it is checked first. A task using ~all of its
        # period is already lapping; the fire count only collapses later, once a
        # backlog has built. Naming it while the count still reads healthy is
        # the entire point of having a detector.
        g = adherence(
            starts=59, starts_window_s=3600, interval_s=60,
            durations_ms=[58_000] * 20,
        )
        assert g["verdict"] == "overruns"
        assert g["p95_over_interval"] == pytest.approx(0.97, abs=0.01)
        assert "58.0s" in g["reason"]

    def test_fast_task_is_not_flagged_as_overrunning(self):
        g = adherence(starts=59, starts_window_s=3600, interval_s=60,
                      durations_ms=[5_000] * 20)
        assert g["verdict"] == "on_schedule"
        assert g["p95_over_interval"] == pytest.approx(0.08, abs=0.01)

    def test_overrun_uses_p95_not_the_last_sample(self):
        # `last_duration_ms` recorded refresh_open_commentary at 8ms — its cheap
        # off-tournament skip — while the same task carried a hard-time-limit
        # Sentry issue. The newest sample is 8ms and would be the only thing the
        # old payload showed; the history is what makes the expensive tenth of
        # its runs visible at all.
        durations = [8] * 18 + [200_000] * 2
        assert durations[0] == 8  # newest-first, i.e. what last_duration_ms saw
        g = adherence(starts=59, starts_window_s=3600, interval_s=60,
                      durations_ms=durations)
        assert g["verdict"] == "overruns"

    def test_overrun_threshold_matches_the_constant(self):
        interval = 100
        under = [int(interval * 1000 * (OVERRUN_RATIO - 0.1))] * 20
        g = adherence(starts=36, starts_window_s=3600, interval_s=interval,
                      durations_ms=under)
        assert g["verdict"] != "overruns"

    def test_terminals_are_reported_alongside_starts(self):
        # "Started 24 times and finished 0" and "never started" are different
        # diagnoses; both numbers travel together so a reader cannot conflate
        # them (CAL-P024b's lesson, carried forward).
        g = adherence(starts=24, starts_window_s=86400, interval_s=3600,
                      terminals=0)
        assert g["starts"] == 24 and g["terminals"] == 0


class TestFindLapping:
    def test_on_schedule_tasks_are_excluded(self):
        graded = {
            "a": adherence(starts=59, starts_window_s=3600, interval_s=60),
            "b": adherence(starts=1, starts_window_s=3600, interval_s=60),
        }
        assert [r["task"] for r in find_lapping(graded)] == ["b"]

    def test_overruns_sort_before_behind_before_unmeasurable(self):
        graded = {
            "unmeasurable": adherence(starts=0, starts_window_s=None,
                                      interval_s=60),
            "behind": adherence(starts=1, starts_window_s=3600, interval_s=60),
            "overruns": adherence(starts=59, starts_window_s=3600, interval_s=60,
                                  durations_ms=[59_000] * 5),
        }
        assert [r["task"] for r in find_lapping(graded)] == [
            "overruns", "behind", "unmeasurable",
        ]

    def test_unmeasurable_is_carried_not_dropped(self):
        # A task nobody can grade is itself a finding — silently omitting it is
        # how "we check everything" becomes true only of what was checkable.
        graded = {"x": adherence(starts=0, starts_window_s=None, interval_s=60)}
        assert len(find_lapping(graded)) == 1

    def test_worse_ratio_sorts_first_among_behind(self):
        graded = {
            "mild": adherence(starts=30, starts_window_s=3600, interval_s=60),
            "severe": adherence(starts=1, starts_window_s=3600, interval_s=60),
        }
        assert [r["task"] for r in find_lapping(graded)][0] == "severe"


class TestExpectedFires:
    def test_basic(self):
        assert expected_fires(3600, 60) == 60.0

    def test_none_inputs(self):
        assert expected_fires(None, 60) is None
        assert expected_fires(3600, None) is None
        assert expected_fires(3600, 0) is None


# ---------------------------------------------------------------------------
# LAT-P071 — the STAMP arm.
#
# The defect: the rate arm needs ``window_s / interval_s >= MIN_EXPECTED_FIRES``,
# and ``window_s`` cannot exceed the counter's TTL. At the production constants
# (86400s, 2.0) that puts a hard 12-hour ceiling on what it can grade, and 33 of
# 123 production beat entries — including five of the six sentinels T5 grades —
# sit above it PERMANENTLY while reporting ``window_too_short``, a string that
# reads as a condition about to clear.
#
# These tests care about the same thing the module already cares about: the
# refusals. The stamp arm may say ``missing`` only when it has evidence, and it
# must never launder "never observed" into "stopped running".
# ---------------------------------------------------------------------------

from app.utils.schedule_adherence import (  # noqa: E402
    STAMP_LATE_TOLERANCE,
    rate_arm_is_structurally_blind,
)

DAY = 86400.0
TTL = 86400.0


class TestRateArmBlindness:
    def test_daily_beat_is_blind_at_production_constants(self):
        # 86400 > 86400/2. The measured production case.
        assert rate_arm_is_structurally_blind(DAY, TTL) is True

    def test_six_hourly_beat_is_not_blind(self):
        # 21600 <= 43200: its counter reaches gradeability in the back half of
        # every TTL cycle. Genuinely transient, and must not be relabelled.
        assert rate_arm_is_structurally_blind(21600.0, TTL) is False

    def test_exactly_at_the_ceiling_is_not_blind(self):
        assert rate_arm_is_structurally_blind(TTL / MIN_EXPECTED_FIRES, TTL) is False

    def test_unknown_ttl_never_asserts_forever(self):
        # "Can never be graded" is a claim about the TTL. Without one, the claim
        # is unsupported, and the honest answer is to fall back to the old words.
        assert rate_arm_is_structurally_blind(DAY, None) is False

    def test_ceiling_moves_with_the_ttl_it_is_derived_from(self):
        # Not transcribed: raise the TTL and the daily beat becomes gradeable.
        assert rate_arm_is_structurally_blind(DAY, 4 * DAY) is False


class TestStampArm:
    def test_blind_beat_with_recent_terminal_is_on_schedule(self):
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=3600.0, counter_ttl_s=TTL)
        assert g["verdict"] == "on_schedule"
        assert g["arm"] == "stamp"
        assert g["stamp_kind"] == "terminal"
        assert g["stamp_age_over_interval"] == 0.04

    def test_late_is_reported_as_a_number_not_a_failure(self):
        # T5's whole claim is "late, never missing". A beat 1.5 intervals stale
        # is late; calling it missing would refute T5 on the detector's opinion.
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=1.5 * DAY, counter_ttl_s=TTL)
        assert g["verdict"] == "on_schedule"
        assert g["stamp_age_over_interval"] == 1.5

    def test_a_whole_missed_fire_is_missing(self):
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=2.5 * DAY, counter_ttl_s=TTL)
        assert g["verdict"] == "missing"
        assert "whole scheduled fire" in g["reason"]

    def test_boundary_is_inclusive_and_does_not_flap(self):
        # Exactly at tolerance is still a pass. The bug being avoided is a
        # correct system crossing its own threshold on a punctual schedule.
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=STAMP_LATE_TOLERANCE * DAY,
                      counter_ttl_s=TTL)
        assert g["verdict"] == "on_schedule"

    def test_start_without_terminal_still_counts_as_having_run(self):
        # T5 protocol branch B. Adherence asks whether the beat FIRED; whether
        # it finished is #1716's open question and has its own flag.
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      terminals=0, newest_terminal_age_s=None,
                      newest_start_age_s=600.0, counter_ttl_s=TTL)
        assert g["verdict"] == "on_schedule"
        assert g["stamp_kind"] == "start"

    def test_no_stamp_at_all_is_unmeasurable_not_missing(self):
        # Gotcha #53. A task never observed is not a task that stopped, and
        # grading it ``missing`` would make this arm worse than the silence it
        # replaces — it would page for every beat the label join cannot see.
        g = adherence(starts=0, starts_window_s=None, interval_s=DAY,
                      counter_ttl_s=TTL)
        assert g["verdict"] == "unmeasurable"
        assert g["arm"] == "stamp"
        assert "no start or terminal stamp" in g["reason"]

    def test_newest_of_the_two_stamps_wins(self):
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=5 * DAY, newest_start_age_s=60.0,
                      counter_ttl_s=TTL)
        assert g["verdict"] == "on_schedule"
        assert g["stamp_kind"] == "start"

    def test_rate_arm_still_wins_when_it_can_speak(self):
        # A blind-by-interval beat whose window somehow DID reach the bar keeps
        # the stronger evidence. The stamp arm is a fallback, not a takeover.
        g = adherence(starts=2, starts_window_s=3 * DAY, interval_s=DAY,
                      newest_terminal_age_s=10 * DAY, counter_ttl_s=TTL)
        assert g["arm"] == "rate"
        assert g["verdict"] != "missing"

    def test_transient_shortfall_keeps_the_rate_arm_and_says_so(self):
        g = adherence(starts=0, starts_window_s=7000, interval_s=21600.0,
                      newest_terminal_age_s=10 * DAY, counter_ttl_s=TTL)
        assert g["arm"] == "rate"
        assert g["verdict"] == "unmeasurable"
        assert "transient" in g["reason"]

    def test_no_ttl_supplied_reproduces_the_old_behaviour_exactly(self):
        # Every existing caller passes no TTL. It must be a pure no-op for them.
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=99 * DAY)
        assert g["arm"] == "rate"
        assert g["verdict"] == "unmeasurable"
        assert g["rate_arm_blind"] is False

    def test_missing_sorts_above_every_other_verdict_in_the_worklist(self):
        graded = {
            "overruns": adherence(starts=59, starts_window_s=3600, interval_s=60,
                                  durations_ms=[59_000] * 5),
            "behind": adherence(starts=1, starts_window_s=3600, interval_s=60),
            "missing": adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                                 newest_terminal_age_s=9 * DAY, counter_ttl_s=TTL),
        }
        assert [r["task"] for r in find_lapping(graded)][0] == "missing"

    def test_the_grader_guard_itself_rejects_a_negative_age(self):
        # The other half of the mutation finding: the grader must not trust its
        # caller to have sanitised the age. A negative age is the freshest
        # possible reading under `age <= limit`, so an unguarded grader would
        # certify a dead beat as healthy the moment any caller skipped the check.
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=-7200.0, counter_ttl_s=TTL)
        assert g["verdict"] == "unmeasurable"
        assert g["stamp_age_s"] is None
