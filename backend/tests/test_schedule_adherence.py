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
        assert g["ratio"] is None
        # LAT-P071 widened the REASON string only: a no-window row now routes to
        # the stamp arm, which says so and — with no stamps supplied, as here —
        # still refuses. The contract this test guards (unmeasurable, never
        # `behind`, no ratio) is unchanged; the wording is strictly more specific.
        assert "no counter window" in g["reason"]
        assert "no start or terminal stamp" in g["reason"]

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


class TestStampArmReachesAMuteRateArm:
    """LAT-P071b — a no-window row takes the stamp arm regardless of interval.

    Found by dry-running the arm against production stamps, not by design.
    `warm_typeahead` has a 10s interval — nowhere near the 12h blindness ceiling
    — but its starts counter had EXPIRED, so `window_s` was None and the rate arm
    was mute. Its last start stamp was 2h55m old against a 10s cadence: 1,050x,
    unambiguously missing, and it is the largest single publisher into the queue
    #1609 is about. A count of unknown age is unusable; a moment is not.
    """

    def test_a_fast_beat_with_no_window_is_graded_on_its_stamp(self):
        g = adherence(starts=0, starts_window_s=None, interval_s=10.0,
                      newest_start_age_s=10_500.0, counter_ttl_s=TTL)
        assert g["arm"] == "stamp"
        assert g["verdict"] == "missing"
        assert g["stamp_age_over_interval"] == 1050.0

    def test_it_says_MUTE_not_BLIND_so_the_message_is_not_nonsense(self):
        # "rate arm blind (interval 10s > 43200s ceiling)" would make a reader
        # correctly conclude the grader is broken. The two routes into this arm
        # are different facts and get different words.
        g = adherence(starts=0, starts_window_s=None, interval_s=10.0,
                      newest_start_age_s=10_500.0, counter_ttl_s=TTL)
        assert "no counter window" in g["reason"]
        assert "blind" not in g["reason"]
        assert g["rate_arm_blind"] is False

    def test_a_YOUNG_window_stays_a_transient_rate_shrug(self):
        # A window that exists but is short will age into gradeability on its
        # own. Routing it to the stamp arm would trade a self-healing silence for
        # a permanent second opinion.
        g = adherence(starts=1, starts_window_s=60, interval_s=600.0,
                      newest_start_age_s=10_500.0, counter_ttl_s=TTL)
        assert g["arm"] == "rate"
        assert "transient" in g["reason"]

    def test_the_absolute_floor_protects_a_fast_beat_from_ordinary_jitter(self):
        # 2 x 10s would call a healthy beat missing after twenty seconds — a
        # deploy restart, one slow upstream call, a worker recycling a child.
        g = adherence(starts=0, starts_window_s=None, interval_s=10.0,
                      newest_start_age_s=120.0, counter_ttl_s=TTL)
        assert g["verdict"] == "on_schedule"

    def test_the_floor_does_not_loosen_a_slow_beat(self):
        # For a daily beat the floor is irrelevant and 2 intervals governs.
        from app.utils.schedule_adherence import STAMP_MIN_TOLERANCE_S
        assert STAMP_MIN_TOLERANCE_S < DAY * STAMP_LATE_TOLERANCE
        g = adherence(starts=1, starts_window_s=77000, interval_s=DAY,
                      newest_terminal_age_s=2.5 * DAY, counter_ttl_s=TTL)
        assert g["verdict"] == "missing"

    def test_no_interval_at_all_still_refuses_outright(self):
        # Without an interval there is nothing to compare an age against, and the
        # stamp arm must not invent one.
        g = adherence(starts=5, starts_window_s=None, interval_s=None,
                      newest_start_age_s=10_500.0, counter_ttl_s=TTL)
        assert g["verdict"] == "unmeasurable"
        assert g["reason"] == "no_interval_or_window"


class TestRateArmConsultsTheStamp:
    """#3276 — a healthy ratio must not outvote a stamp that says nothing ran.

    Reproduces the production reading of 2026-09-05 that these guard against:
    ``prewarm_live_feed_shapes``, the beat keeping Discover and Sports warm, was
    dead for 3h43m on a 40s interval and graded ``on_schedule`` with an empty
    reason — because 3.7h of death inside a 21h counter window left the ratio at
    0.70, above ``BEHIND_RATIO``. The stamp proving it was passed in and unread.

    The pairs below are deliberate. Every "it now alarms" case is written beside
    the case that must still stay quiet, because the failure mode of this fix is
    an alarm generator, not a miss.
    """

    #: The production row, to the field. 40s beat, 21h window, 1327 fires.
    PROD = dict(starts=1327, starts_window_s=75698.0, interval_s=40.0,
                deliveries=1327, deliveries_window_s=75698.0,
                durations_ms=[20135] * 50, counter_ttl_s=TTL)

    def test_the_production_reading_that_said_on_schedule_now_says_missing(self):
        g = adherence(**self.PROD, newest_start_age_s=13_374.0)
        assert g["verdict"] == "missing"
        # The ratio is still reported and is still healthy-looking. The point is
        # not that the count was wrong; it is that the count could not see this.
        assert g["ratio"] >= BEHIND_RATIO
        assert g["stamp_age_over_interval"] == 334.35
        # The reason must name BOTH numbers, or a reader cannot tell why a row
        # with a fine ratio is red.
        assert "3.7h" in g["reason"] and "0.70" in g["reason"]

    def test_the_same_row_with_a_fresh_stamp_stays_on_schedule(self):
        # The other direction, and the one that decides whether this is safe to
        # ship: an identical row whose beat is actually running must not move.
        g = adherence(**self.PROD, newest_start_age_s=12.0)
        assert g["verdict"] == "on_schedule"
        assert g["stamp_age_s"] == 12.0

    def test_late_is_not_missing(self):
        # `_grade_on_stamp`'s standing contract — "late, never missing" — is not
        # allowed to mean something different on this arm. At a 40s interval the
        # 300s FLOOR governs, not 2x the interval, so 299s of jitter is quiet.
        assert adherence(**self.PROD,
                         newest_start_age_s=299.0)["verdict"] == "on_schedule"
        assert adherence(**self.PROD,
                         newest_start_age_s=301.0)["verdict"] == "missing"

    def test_no_stamp_at_all_leaves_the_verdict_alone(self):
        # Gotcha #53. An absent observation is not an observed absence: a task
        # nobody has ever stamped must not be reported as one that stopped.
        g = adherence(**self.PROD)
        assert g["verdict"] == "on_schedule"
        assert g["stamp_age_s"] is None

    def test_a_future_stamp_cannot_certify_a_dead_beat_on_this_arm_either(self):
        # The negative-age guard, which is why `_newest_stamp` is shared. A
        # clock-skewed stamp is the freshest possible reading under `age > tol`
        # and would silently re-open the exact hole this closes.
        g = adherence(**self.PROD, newest_start_age_s=-7200.0)
        assert g["stamp_age_s"] is None
        assert g["verdict"] == "on_schedule"

    def test_only_the_START_stamp_may_veto_a_healthy_rate(self):
        # The asymmetry this arm turns on, and the case that caught the first
        # draft of this fix. A stale TERMINAL is compatible with a beat that is
        # firing and hanging — that is #1716's question, it already has
        # `never_completes`, and answering it here would decide it by accident.
        # Only a stale START proves the beat did not fire.
        g = adherence(**self.PROD, newest_terminal_age_s=13_374.0)
        assert g["verdict"] == "on_schedule"
        assert g["stamp_age_s"] is None

        # The row from `TestStampArm::test_rate_arm_still_wins_when_it_can_speak`,
        # restated here so the two arms' contracts are asserted side by side:
        # 2 starts counted in 3 days against a terminal 10 days old is a task
        # that runs and never completes, not a missing beat.
        g2 = adherence(starts=2, starts_window_s=3 * DAY, interval_s=DAY,
                       newest_terminal_age_s=10 * DAY, counter_ttl_s=TTL)
        assert g2["arm"] == "rate"
        assert g2["verdict"] != "missing"

    def test_missing_beats_overruns_when_the_beat_is_both(self):
        # A dead beat whose stale duration ring still reads as lapping. Absent
        # outranks lapping: it is not overrunning, it is not running. Ordering
        # matters because `overruns` returns early.
        g = adherence(starts=1243, starts_window_s=61153.0, interval_s=30.0,
                      deliveries=1890, deliveries_window_s=61153.0,
                      durations_ms=[195292] * 50,
                      newest_start_age_s=13_374.0, counter_ttl_s=TTL)
        assert g["p95_over_interval"] >= OVERRUN_RATIO
        assert g["verdict"] == "missing"

    def test_a_lapping_but_LIVE_beat_still_reads_overruns(self):
        # The pair to the above: same row, fresh stamp. #2014's four expiring
        # beats live here — they ARE running, so this fix must not touch them.
        g = adherence(starts=1243, starts_window_s=61153.0, interval_s=30.0,
                      deliveries=1890, deliveries_window_s=61153.0,
                      durations_ms=[195292] * 50,
                      newest_start_age_s=15.0, counter_ttl_s=TTL)
        assert g["verdict"] == "overruns"

    def test_a_genuinely_behind_beat_is_still_behind_not_missing(self):
        # `behind` must not be swallowed by the new verdict when the beat is
        # merely slow rather than absent.
        g = adherence(starts=100, starts_window_s=60000.0, interval_s=60.0,
                      deliveries=100, deliveries_window_s=60000.0,
                      durations_ms=[500] * 50,
                      newest_start_age_s=30.0, counter_ttl_s=TTL)
        assert g["ratio"] < BEHIND_RATIO
        assert g["verdict"] == "behind"

    def test_the_dead_rail_reaches_the_top_of_the_work_list(self):
        # A verdict nobody reads is not a fix. `missing` already sorts first in
        # `find_lapping`; this asserts the new producer actually lands there.
        graded = {
            "app.tasks.poll_all_odds": adherence(
                starts=1243, starts_window_s=61153.0, interval_s=30.0,
                durations_ms=[195292] * 50, newest_start_age_s=15.0,
                counter_ttl_s=TTL),
            "app.tasks.prewarm_live_feed_shapes": adherence(
                **self.PROD, newest_start_age_s=13_374.0),
        }
        assert find_lapping(graded)[0]["task"] == (
            "app.tasks.prewarm_live_feed_shapes")

    def test_two_dead_beats_rank_by_deadness_not_by_ratio(self):
        # #3276: measured on production — three beats read `missing` at once,
        # so which one tops the work-list is a real question and `ratio` is the
        # wrong answer to it. The warm rail silent for 348 of its own intervals
        # must outrank a beat silent for 5, even though the rail's ratio (0.70)
        # is the HEALTHIER-looking of the two.
        graded = {
            "app.tasks.refresh_open_commentary": adherence(
                starts=90, starts_window_s=60000.0, interval_s=180.0,
                deliveries=90, deliveries_window_s=60000.0,
                newest_start_age_s=827.0, counter_ttl_s=TTL),
            "app.tasks.prewarm_live_feed_shapes": adherence(
                **self.PROD, newest_start_age_s=13_914.0),
        }
        assert all(g["verdict"] == "missing" for g in graded.values())
        # The rail has the higher ratio and must still sort first.
        assert (graded["app.tasks.prewarm_live_feed_shapes"]["ratio"]
                > graded["app.tasks.refresh_open_commentary"]["ratio"])
        assert [r["task"] for r in find_lapping(graded)] == [
            "app.tasks.prewarm_live_feed_shapes",
            "app.tasks.refresh_open_commentary",
        ]
