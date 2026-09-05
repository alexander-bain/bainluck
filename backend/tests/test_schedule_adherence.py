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
    SELF_GATE_MATERIAL_RATIO,
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

    # CERT-1932: these two carried `starts=1243, deliveries=1890` — a 34%
    # self-gate rate and a 195s p95, which is not a generic lapping beat, it is
    # `poll_all_odds`. So the first of the pair was asserting the exact false
    # `missing` the CERT-1932 BLOCK named, with the false positive written in as
    # the expected value. The property each test actually exists for — that
    # `missing` outranks `overruns`, and that a live lapping beat is untouched —
    # is independent of self-gating, so the gate is removed from the fixture
    # (`starts == deliveries`) and the property is tested on its own. The
    # self-gating row now has its own class below.
    def test_missing_beats_overruns_when_the_beat_is_both(self):
        # A dead beat whose stale duration ring still reads as lapping. Absent
        # outranks lapping: it is not overrunning, it is not running. Ordering
        # matters because `overruns` returns early.
        g = adherence(starts=1243, starts_window_s=61153.0, interval_s=30.0,
                      deliveries=1243, deliveries_window_s=61153.0,
                      durations_ms=[195292] * 50,
                      newest_start_age_s=13_374.0, counter_ttl_s=TTL)
        assert g["p95_over_interval"] >= OVERRUN_RATIO
        assert g["verdict"] == "missing"

    def test_a_lapping_but_LIVE_beat_still_reads_overruns(self):
        # The pair to the above: same row, fresh stamp. #2014's four expiring
        # beats live here — they ARE running, so this fix must not touch them.
        g = adherence(starts=1243, starts_window_s=61153.0, interval_s=30.0,
                      deliveries=1243, deliveries_window_s=61153.0,
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


class TestASelfGatingBeatIsNotAnAbsentOne:
    """CERT-1932 — the #3276 stamp veto must not fire on a task that self-gates.

    The first presentation of #3276 shipped the veto above and graded a HEALTHY
    ``poll_all_odds`` as ``missing``: 20/20 deliveries, 19 self-gated fires,
    ratio 1.0, and a 301s start age, because that task drops to a 600s adaptive
    cadence when no sport is live and its gate sits BEFORE ``_tracked_run`` — so
    no start is stamped on a gated fire. A stale start stamp is the expected
    reading of a perfectly healthy self-gating beat.

    Both halves are asserted together in every test here, because the whole
    risk of this repair is that it buys the false negative back by disarming
    the veto that #3276 exists to arm.
    """

    #: The graded row, to the field, from the CERT-1932 BLOCK.
    GATED = dict(starts=1, starts_window_s=600.0, interval_s=30.0,
                 deliveries=20, deliveries_window_s=600.0,
                 durations_ms=[900] * 20, counter_ttl_s=TTL)

    #: The dead rail, to the field, from production 2026-09-05 19:00Z. Unequal
    #: windows on purpose: this is the real pair, and 1327/79469 vs 1327/80011
    #: is a 0.68% gate — the number that must stay under the threshold.
    DEAD_RAIL = dict(starts=1327, starts_window_s=80011.0, interval_s=40.0,
                     deliveries=1327, deliveries_window_s=79469.0,
                     durations_ms=[20135] * 50, counter_ttl_s=TTL)

    def test_the_graded_row_that_falsely_read_missing_no_longer_does(self):
        g = adherence(**self.GATED, newest_start_age_s=301.0)
        assert g["verdict"] != "missing"
        # The gate is MEASURED, not assumed: 19 of 20 fires declined.
        assert g["self_gate_fraction"] == 0.95
        # ...and the withheld veto is on the row. `on_schedule` with an empty
        # reason was the original #3276 defect; a tolerated 10x stamp with no
        # note would be that same silence wearing the fix's clothes.
        assert "self-gate" in g["stamp_veto_withheld"]
        assert "10.03x" in g["stamp_veto_withheld"]

    def test_the_dead_rail_measured_beside_it_still_reads_missing(self):
        # The other half of the BLOCK's required regression, on the real
        # production windows rather than the idealised equal ones.
        g = adherence(**self.DEAD_RAIL, newest_start_age_s=17_500.0)
        assert g["verdict"] == "missing"
        # 0.68%, an order of magnitude clear of the threshold either way.
        assert g["self_gate_fraction"] < SELF_GATE_MATERIAL_RATIO
        assert g["stamp_veto_withheld"] is None

    def test_the_two_rows_separate_by_more_than_the_threshold(self):
        # The margin is the claim. If these ever converge the discriminator has
        # stopped discriminating, and a test asserting only the two verdicts
        # would still pass while sitting on a knife edge.
        gated = adherence(**self.GATED, newest_start_age_s=301.0)
        dead = adherence(**self.DEAD_RAIL, newest_start_age_s=17_500.0)
        assert gated["self_gate_fraction"] > SELF_GATE_MATERIAL_RATIO * 5
        assert dead["self_gate_fraction"] < SELF_GATE_MATERIAL_RATIO / 5

    def test_a_self_gating_beat_that_ALSO_stops_being_delivered_is_caught(self):
        # The residual hole, bounded deliberately. Withholding the veto costs a
        # self-gating task its stamp-based detection, so the RATE arm must still
        # be able to catch it — otherwise this repair would make `poll_all_odds`
        # undetectable rather than correctly graded.
        g = adherence(starts=1, starts_window_s=600.0, interval_s=30.0,
                      deliveries=2, deliveries_window_s=600.0,
                      durations_ms=[900] * 2, counter_ttl_s=TTL,
                      newest_start_age_s=301.0)
        assert g["verdict"] == "behind"

    def test_windows_that_drift_still_yield_a_usable_fraction(self):
        # Why the fraction is rates and not the existing `self_gated_fires`
        # subtraction. Production's real `poll_all_odds` pair drifts 23.9%, far
        # past SELF_GATE_WINDOW_TOLERANCE, so `self_gated_fires` is None there —
        # and a veto keyed on it would have fired on the live row.
        g = adherence(starts=1318, starts_window_s=49447.0, interval_s=30.0,
                      deliveries=2024, deliveries_window_s=64957.0,
                      durations_ms=[107902] * 50, counter_ttl_s=TTL,
                      newest_start_age_s=3600.0)
        assert g["self_gated_fires"] is None      # the subtraction refuses
        assert g["self_gate_fraction"] == 0.145   # the rate does not
        assert g["verdict"] != "missing"

    def test_no_delivery_counter_withholds_the_veto_and_says_so(self):
        # Gotcha #53 in the small: with no deliveries there is nothing to
        # compare a start rate against, so the module cannot tell a gate from a
        # grave. It must not assert the sharpest verdict it owns off evidence it
        # does not have — but it must not go silent about that either.
        g = adherence(starts=1327, starts_window_s=80011.0, interval_s=40.0,
                      durations_ms=[20135] * 50, counter_ttl_s=TTL,
                      newest_start_age_s=17_500.0)
        assert g["verdict"] != "missing"
        assert g["self_gate_fraction"] is None
        assert "no delivery counter" in g["stamp_veto_withheld"]

    def test_a_fresh_stamp_never_records_a_withheld_veto(self):
        # The field means "the veto was considered and declined". A punctual
        # beat never reached that decision, and stamping it with a note would
        # make the field unreadable as a signal.
        g = adherence(**self.GATED, newest_start_age_s=5.0)
        assert g["stamp_veto_withheld"] is None
        assert g["self_gate_fraction"] == 0.95

    def test_every_row_carries_both_fields_whatever_graded_it(self):
        # Payload shape must not depend on the branch. A key that appears only
        # sometimes makes `.get()` mean two things to a reader.
        for row in (adherence(**self.GATED, newest_start_age_s=5.0),
                    adherence(**self.DEAD_RAIL, newest_start_age_s=17_500.0),
                    adherence(starts=0, starts_window_s=10.0, interval_s=30.0)):
            assert "self_gate_fraction" in row and "stamp_veto_withheld" in row


class TestAHistoryIsNotAHeartbeat:
    """CERT-1943 — the self-gate exemption needs a MOMENT, not a whole-window average.

    The CERT-1932 repair above withheld the stale-start veto whenever a task
    self-gated materially, and closed its own note with "the fires are
    arriving". On the evidence it had, it could not know that.
    ``self_gate_fraction`` divides 24h of deliveries by 24h of starts, so a
    mature self-gating task that stopped dead five minutes ago carries exactly
    the fraction it carried while healthy — five minutes moves a day-long
    average by nothing. The veto went on being withheld and the beat read
    ``on_schedule``.

    This is the module's founding defect (#1790) a third time, one field
    further right: an average over a long window cannot see a hole much
    shorter than the window. So the exemption now also requires a fresh
    DELIVERY — the observable consequence of the self-gate story ("the fire
    was delivered and the body declined"). When deliveries have stopped too,
    nothing is being declined.

    Every test asserts BOTH halves together, for the same reason the class
    above does: the risk of this repair is buying CERT-1932's false positive
    back.
    """

    #: The graded row from the CERT-1943 BLOCK, to the field. Equal 86400s
    #: windows, a mature counter pair, and a start stamp 10 periods old.
    #: Yields ratio 1.0 and self_gate_fraction 0.145 — a materially
    #: self-gating task, so the CERT-1932 exemption applies to it.
    MATURE = dict(starts=2462, starts_window_s=86400.0, interval_s=30.0,
                  deliveries=2880, deliveries_window_s=86400.0,
                  counter_ttl_s=TTL)

    #: The non-self-gating dead rail the BLOCK requires be retained, on the
    #: real production windows: 1327/79469 vs 1327/80011 is a 0.68% gate.
    DEAD_RAIL = dict(starts=1327, starts_window_s=80011.0, interval_s=40.0,
                     deliveries=1327, deliveries_window_s=79469.0,
                     durations_ms=[20135] * 50, counter_ttl_s=TTL)

    def test_the_blocked_row_still_reads_on_schedule_when_a_delivery_is_fresh(self):
        # HALF ONE of the required regression. This is the CERT-1932 property
        # and it must survive: a self-gating beat whose fires ARE still
        # arriving is healthy, however stale its start stamp.
        g = adherence(**self.MATURE, newest_start_age_s=301.0,
                      newest_delivery_age_s=5.0)
        assert g["verdict"] != "missing"
        assert g["self_gate_fraction"] == 0.145
        assert g["delivery_age_s"] == 5.0
        # The withheld veto now cites the moment, not just the history.
        assert "a delivery landed 5s ago" in g["stamp_veto_withheld"]

    def test_the_blocked_row_reads_missing_when_the_deliveries_stopped_too(self):
        # HALF TWO, and the defect CERT-1943 named: IDENTICAL counters, an
        # identical start stamp, an identical self-gate fraction — the only
        # thing that changed is that the delivery moment went stale, and that
        # alone must flip the verdict.
        g = adherence(**self.MATURE, newest_start_age_s=301.0,
                      newest_delivery_age_s=301.0)
        assert g["verdict"] == "missing"
        # Same history as the row above, so the fraction cannot be what
        # distinguishes them — which is exactly why the fraction was never
        # enough on its own.
        assert g["self_gate_fraction"] == 0.145
        assert g["stamp_veto_withheld"] is None
        # `missing` beside a 15% gate rate invites the objection the exemption
        # exists to answer, so the row pre-empts it with the fact that
        # overrode it.
        assert "nothing arriving for the gate to decline" in g["reason"]

    def test_the_two_halves_differ_only_in_the_delivery_moment(self):
        # Stated as one assertion because it is the whole repair: same task,
        # same counters, same stamp, opposite verdicts.
        fresh = adherence(**self.MATURE, newest_start_age_s=301.0,
                          newest_delivery_age_s=5.0)
        stale = adherence(**self.MATURE, newest_start_age_s=301.0,
                          newest_delivery_age_s=301.0)
        assert (fresh["ratio"], stale["ratio"]) == (1.0, 1.0)
        assert fresh["self_gate_fraction"] == stale["self_gate_fraction"]
        assert fresh["stamp_age_s"] == stale["stamp_age_s"]
        assert fresh["verdict"] != stale["verdict"]

    def test_an_unstamped_delivery_is_unknown_and_does_not_grade_missing(self):
        # GOTCHA #53, and the reason this is three-state. Delivery counters
        # carry a 24h TTL and survive a dyno restart; this stamp is written
        # fresh. So for one interval after every deploy a HEALTHY self-gating
        # beat has a live counter and no stamp — and reading that gap as
        # staleness would grade `poll_all_odds` `missing` after every release,
        # which is precisely CERT-1932's false positive bought back.
        g = adherence(**self.MATURE, newest_start_age_s=301.0,
                      newest_delivery_age_s=None)
        assert g["verdict"] != "missing"
        assert g["delivery_age_s"] is None
        # It says which of the two it is rather than implying it measured one.
        assert "no delivery has been stamped yet" in g["stamp_veto_withheld"]
        assert "unknown" in g["stamp_veto_withheld"]

    def test_the_non_self_gating_dead_rail_control_is_retained(self):
        # The BLOCK requires this control survive. A rail that does NOT
        # self-gate never reaches the exemption at all, so its verdict must
        # not depend on the delivery moment in any of the three states.
        for delivery_age in (5.0, 17_500.0, None):
            g = adherence(**self.DEAD_RAIL, newest_start_age_s=17_500.0,
                          newest_delivery_age_s=delivery_age)
            assert g["verdict"] == "missing", delivery_age
            assert g["self_gate_fraction"] == 0.007, delivery_age
            assert g["stamp_veto_withheld"] is None, delivery_age

    def test_a_fresh_delivery_cannot_rescue_a_rail_that_does_not_self_gate(self):
        # The mirror of the test above, stated on its own because it is the
        # failure mode a reader will fear: that adding a delivery signal gave
        # dead beats a second way to look alive. It did not — the delivery
        # moment only ever NARROWS an exemption that already required a
        # material gate rate.
        g = adherence(**self.DEAD_RAIL, newest_start_age_s=17_500.0,
                      newest_delivery_age_s=1.0)
        assert g["verdict"] == "missing"
        assert "nothing started for 4.9h" in g["reason"]
        # ...and it does NOT append the self-gate clause, because 0.7% is not
        # a material gate and claiming otherwise would misdescribe the row.
        assert "gate to decline" not in g["reason"]

    def test_a_future_delivery_stamp_cannot_certify_a_dead_beat(self):
        # Ahead-drift, the rule `_stamp_ages_s` already carries. A negative
        # age passes every `<= tolerance` test as the freshest possible
        # reading, so a clock-skewed stamp would withhold the veto on a beat
        # that genuinely stopped. It must read as unknown, not as fresh.
        g = adherence(**self.MATURE, newest_start_age_s=301.0,
                      newest_delivery_age_s=-50.0)
        assert g["delivery_age_s"] is None
        assert "no delivery has been stamped yet" in g["stamp_veto_withheld"]

    def test_delivery_freshness_uses_the_same_tolerance_as_the_start_stamp(self):
        # The two moments must not drift apart on what "stale" means — both
        # go through `_stamp_tolerance_s`, which is max(2x interval, 300s).
        # Either side of the 300s floor, one second apart.
        quiet = adherence(**self.MATURE, newest_start_age_s=301.0,
                          newest_delivery_age_s=299.0)
        red = adherence(**self.MATURE, newest_start_age_s=301.0,
                        newest_delivery_age_s=301.0)
        assert quiet["verdict"] != "missing"
        assert red["verdict"] == "missing"

    def test_delivery_age_is_published_on_every_row(self):
        # Same contract as the two fields CERT-1932 added: defaulted
        # everywhere, so `.get()` never means two things to a reader.
        for row in (adherence(**self.MATURE, newest_start_age_s=5.0),
                    adherence(**self.DEAD_RAIL, newest_start_age_s=17_500.0),
                    adherence(starts=0, starts_window_s=10.0, interval_s=30.0)):
            assert "delivery_age_s" in row

    def test_a_healthy_beat_is_untouched_by_all_of_this(self):
        # The silence case beside every alarm case. A beat with a FRESH start
        # stamp never reaches the veto at all, so no combination of delivery
        # states may change its grade.
        for delivery_age in (5.0, 99_999.0, None, -3.0):
            g = adherence(**self.MATURE, newest_start_age_s=5.0,
                          newest_delivery_age_s=delivery_age)
            assert g["verdict"] == "on_schedule", delivery_age
            assert g["stamp_veto_withheld"] is None, delivery_age


class TestEmitSideCounterSaysWhichEndLostTheFires:
    """LAT-P238-EMIT-SIDE-COUNTER (#3268, #3251), as repaired under CERT-1966.

    THE MEASUREMENT THAT FORCED THE FIELD. Over 28.9 minutes on 2026-09-05
    ``prewarm_live_feed_shapes`` delivered **0.646** of its scheduled fires with
    ``starts == deliveries`` EXACTLY (+28/+28) and ``self_gated_fires`` +0.
    Every counter the module had was taken at-or-after delivery, so that
    localised the loss to *before* delivery and could go no further — and the
    two causes that fit it need opposite fixes: beat is not emitting at 40s, or
    the broker is expiring messages before delivery.

    THE DEFECT THAT FORCED THE REPAIR. The first version compared a new emission
    RATE against the 24h delivery counter's rate. Dividing by each counter's own
    age fixes the unit mismatch and not the population mismatch: the emission
    counter is born at the deploy while the delivery counter deliberately holds
    up to a day of PRE-deploy behaviour. So the counts are now taken into shared
    wall-clock buckets, and ``TestTheTwoHistoriesMustReadDifferently`` below is
    the regression CERT-1966 named.
    """

    #: A 40s beat on a 600s bucket: 15 fires per bucket. Half of them published
    #: and never delivered. The 24h counters are also short (ratio 0.50, i.e.
    #: `behind`) because that is the branch that gets to say which end.
    BROKER_LOSS = dict(
        starts=1080, starts_window_s=86400.0,
        deliveries=1080, deliveries_window_s=86400.0,
        interval_s=40.0, terminals=1079,
        matched_emitted=15, matched_delivered=7,
        matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
    )

    #: The same shortfall arriving from the other end: beat published only 7 in
    #: the bucket and all 7 were delivered.
    BEAT_LOSS = dict(
        starts=1080, starts_window_s=86400.0,
        deliveries=1080, deliveries_window_s=86400.0,
        interval_s=40.0, terminals=1079,
        matched_emitted=7, matched_delivered=7,
        matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
    )

    # --- RED FIRST --------------------------------------------------------

    def test_the_broker_loss_shape_goes_red(self):
        g = adherence(**self.BROKER_LOSS)
        assert g["undelivered_fraction"] == pytest.approx(8 / 15, abs=0.005)
        assert g["verdict"] == "behind"
        assert "never reached a worker" in g["reason"]
        assert "not at the scheduler" in g["reason"]

    def test_the_beat_loss_shape_reads_the_opposite_end(self):
        g = adherence(**self.BEAT_LOSS)
        assert g["undelivered_fraction"] == 0.0
        assert g["verdict"] == "behind"
        assert "SCHEDULER" in g["reason"]
        assert "never reached a worker" not in g["reason"]

    def test_the_two_shapes_differ_only_in_the_bucket_delivery_count(self):
        broker, beat = dict(self.BROKER_LOSS), dict(self.BEAT_LOSS)
        differing = {k for k in broker if broker[k] != beat.get(k)}
        assert differing == {"matched_emitted"}
        a, b = adherence(**broker), adherence(**beat)
        assert a["ratio"] == b["ratio"]
        assert a["deliveries"] == b["deliveries"]
        assert a["undelivered_fraction"] != b["undelivered_fraction"]


class TestTheTwoHistoriesMustReadDifferently:
    """CERT-1966's named regression: a change-point must survive the average.

    The block, verbatim. These two histories produce IDENTICAL aggregate inputs
    — 90 emitted in 3600s against 1080 delivered in 86400s:

    * current hour healthy: 90 emitted, 90 delivered, plus 990 deliveries in the
      preceding 23 hours. True current undelivered fraction **0%**.
    * current hour broken: 90 emitted, 45 delivered, plus 1,035 deliveries in
      the preceding 23 hours. True current undelivered fraction **50%**.

    The blocked version rendered BOTH as ``undelivered_fraction: 0.5`` with the
    sentence naming the broker. On a rail whose queue had just been moved that
    sends the repair to the wrong subsystem — which is a ship failure, not a
    guard gap: the DISCOVER ship here is deciding whether the warm rail loses
    fires at the scheduler or after publication.

    The requirement, in the block's words: *changing only pre-counter delivery
    history must not change the current diagnosis.*
    """

    #: Everything the two histories share, including the aggregate counters that
    #: made them indistinguishable. `deliveries`/`deliveries_window_s` are the
    #: 24h numbers; only their SPLIT between the current hour and the preceding
    #: 23 differs, and nothing in the aggregate can see that split.
    COMMON = dict(
        starts=1080, starts_window_s=86400.0,
        deliveries=1080, deliveries_window_s=86400.0,
        interval_s=40.0, terminals=1080,
        matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
    )

    #: 90 publications in the current hour is 15 per 600s bucket.
    HEALTHY = dict(COMMON, matched_emitted=15, matched_delivered=15)
    BROKEN = dict(COMMON, matched_emitted=15, matched_delivered=7)

    def test_the_aggregate_inputs_really_are_identical(self):
        # The control that makes the rest of this class a regression rather
        # than two unrelated fixtures. If these ever diverge, the test has
        # stopped reproducing the block's counterexample.
        agg = ("starts", "starts_window_s", "deliveries", "deliveries_window_s",
               "interval_s", "terminals")
        assert {k: self.HEALTHY[k] for k in agg} == {k: self.BROKEN[k] for k in agg}

    def test_the_healthy_history_reads_zero(self):
        g = adherence(**self.HEALTHY)
        assert g["undelivered_fraction"] == 0.0
        assert "never reached a worker" not in g["reason"]

    def test_the_broken_history_reads_the_loss(self):
        g = adherence(**self.BROKEN)
        assert g["undelivered_fraction"] == pytest.approx(8 / 15, abs=0.005)
        assert "never reached a worker" in g["reason"]

    def test_pre_counter_history_cannot_move_the_current_diagnosis(self):
        # The block's exact requirement. Sweep the 24h delivery total across
        # everything the preceding 23 hours could have held — including the two
        # values from the counterexample — and the matched reading must not
        # move at all.
        readings = set()
        for legacy_total in (0, 500, 990, 1035, 1080, 2160):
            g = adherence(**{**self.BROKEN, "deliveries": legacy_total})
            readings.add(g["undelivered_fraction"])
        # NOT `assert readings.pop() == ...`: a mutating call inside an
        # assert is stripped with the assert under `-O`, so the check quietly
        # stops running (CodeQL py/side-effect-in-assert).
        assert len(readings) == 1, readings
        only = next(iter(readings))
        assert only == pytest.approx(8 / 15, abs=0.005)

    def test_the_legacy_window_cannot_move_it_either(self):
        readings = {
            adherence(**{**self.BROKEN, "deliveries_window_s": w})[
                "undelivered_fraction"]
            for w in (600.0, 3600.0, 43200.0, 86400.0)
        }
        assert len(readings) == 1

    def test_the_matched_pair_is_the_only_input_that_moves_it(self):
        base = adherence(**self.BROKEN)["undelivered_fraction"]
        moved = adherence(**{**self.BROKEN, "matched_delivered": 15})[
            "undelivered_fraction"]
        assert base != moved and moved == 0.0


class TestTheMatchedFractionRefusesWhatItCannotSee:
    """Unknown is not zero, and a partial cohort is not a measurement."""

    BASE = dict(
        starts=1080, starts_window_s=86400.0,
        deliveries=1080, deliveries_window_s=86400.0,
        interval_s=40.0, terminals=1079,
        matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
    )

    def test_an_unseen_delivery_writer_is_unknown_not_total_loss(self):
        # `matched_delivered=None` is the state of the WHOLE fleet for one
        # bucket after the release that ships the bucketed delivery writer.
        # Reading it as 0 would report 100% broker loss on every beat in the
        # schedule at the exact moment the instrument is first trusted.
        g = adherence(**self.BASE, matched_emitted=15, matched_delivered=None)
        assert g["undelivered_fraction"] is None
        assert "never reached a worker" not in g["reason"]
        assert "SCHEDULER" not in g["reason"]

    def test_a_real_zero_is_reported_as_total_loss(self):
        # The mirror, and the reading this instrument most needs to be able to
        # make: the writer IS live (0, not None) and this task got nothing.
        g = adherence(**self.BASE, matched_emitted=15, matched_delivered=0)
        assert g["undelivered_fraction"] == 1.0
        assert "never reached a worker" in g["reason"]

    def test_no_bucket_at_all_is_unknown(self):
        g = adherence(**self.BASE)
        assert g["undelivered_fraction"] is None
        assert g["matched_emitted"] is None and g["matched_delivered"] is None

    def test_too_few_publications_to_grade_is_unknown(self):
        # The same refusal the rate arm makes at `MIN_EXPECTED_FIRES`: at one
        # publication in the bucket, observing zero deliveries is not evidence
        # of anything, and a detector that manufactures 100% from one sample
        # gets muted — which is worse than not having it.
        for emitted in (0, 1):
            g = adherence(**self.BASE, matched_emitted=emitted,
                          matched_delivered=0)
            assert g["undelivered_fraction"] is None, emitted
        g = adherence(**self.BASE, matched_emitted=2, matched_delivered=0)
        assert g["undelivered_fraction"] == 1.0

    def test_more_deliveries_than_publications_clamps_to_zero(self):
        # The bucket boundary: a message published at second 599 is delivered
        # in the next bucket, so the count can lean either way at the edge.
        g = adherence(**self.BASE, matched_emitted=15, matched_delivered=17)
        assert g["undelivered_fraction"] == 0.0

    def test_one_spilled_fire_is_never_editorialised_about(self):
        # 1 of 15 is 6.7%, under the fraction floor.
        quiet = adherence(**self.BASE, matched_emitted=15, matched_delivered=14)
        assert quiet["undelivered_fraction"] == pytest.approx(1 / 15, abs=0.005)
        assert "never reached a worker" not in quiet["reason"]
        # And on a SLOW beat one spilled fire is a huge fraction of a small
        # bucket, which no fraction threshold can cover — hence the absolute
        # term. 1 of 2 is 50% and must still stay quiet.
        #
        # Both rows below are forced onto the `behind` branch (300s interval,
        # 100 deliveries against 288 scheduled = ratio 0.35). Without that they
        # would grade `on_schedule` with an EMPTY reason and the
        # "not in reason" assertion would pass vacuously — a dead assertion
        # reads exactly like a working one.
        slow_base = {**self.BASE, "interval_s": 300.0, "deliveries": 100,
                     "starts": 100, "terminals": 100}
        slow = adherence(**slow_base, matched_emitted=2, matched_delivered=1)
        assert slow["verdict"] == "behind"
        assert slow["undelivered_fraction"] == 0.5
        assert slow["bucket_attribution"] == "current_bucket_healthy"
        assert "never reached a worker" not in slow["reason"]
        assert "this window is healthy" in slow["reason"]   # it DID speak
        # Two fires missing out of three is not spill.
        real = adherence(**slow_base, matched_emitted=3, matched_delivered=1)
        assert real["verdict"] == "behind"
        assert real["bucket_attribution"] == "broker_or_worker"
        assert "never reached a worker" in real["reason"]


class TestTheMatchedPairIsReportedNeverGraded:
    BASE = dict(
        starts=1080, starts_window_s=86400.0,
        deliveries=1080, deliveries_window_s=86400.0,
        interval_s=40.0, terminals=1079,
        matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
    )

    def test_the_matched_pair_never_moves_the_ratio_or_the_numerator(self):
        plain = adherence(**self.BASE)
        for emitted, delivered in ((0, 0), (15, 0), (15, 15), (100_000, 1)):
            g = adherence(**self.BASE, matched_emitted=emitted,
                          matched_delivered=delivered)
            assert g["ratio"] == plain["ratio"], (emitted, delivered)
            assert g["numerator"] == plain["numerator"] == "deliveries"
            assert g["verdict"] == plain["verdict"], (emitted, delivered)

    def test_the_matched_pair_is_never_folded_into_self_gated_fires(self):
        plain = adherence(**self.BASE)
        loud = adherence(**self.BASE, matched_emitted=100_000,
                         matched_delivered=1)
        assert loud["self_gated_fires"] == plain["self_gated_fires"]
        assert loud["self_gate_fraction"] == plain["self_gate_fraction"]

    def test_a_healthy_beat_is_not_made_unhealthy_by_the_new_fields(self):
        g = adherence(
            starts=2160, starts_window_s=86400.0,
            deliveries=2160, deliveries_window_s=86400.0,
            interval_s=40.0, terminals=2160,
            matched_emitted=15, matched_delivered=15,
            matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
        )
        assert g["verdict"] == "on_schedule"
        assert g["undelivered_fraction"] == 0.0

    def test_every_field_is_on_every_row_whatever_graded_it(self):
        # Four different returns: unmeasurable, window_too_short, the stamp
        # arm, and behind.
        rows = [
            adherence(starts=0, starts_window_s=None, interval_s=None),
            adherence(starts=1, starts_window_s=10.0, interval_s=40.0),
            adherence(starts=0, starts_window_s=None, interval_s=86400.0,
                      newest_start_age_s=10.0, counter_ttl_s=86400.0),
            adherence(**self.BASE, matched_emitted=15, matched_delivered=7),
        ]
        for row in rows:
            for f in ("matched_emitted", "matched_delivered", "matched_bucket_s",
                      "matched_bucket_start", "undelivered_fraction",
                      "deliveries_window_s"):
                assert f in row, f

    def test_the_row_shows_the_span_the_two_counts_describe(self):
        # A reader asked to trust that two numbers are a matched cohort has to
        # be able to see WHICH span they matched over, or the claim is
        # unfalsifiable from the payload.
        g = adherence(**self.BASE, matched_emitted=15, matched_delivered=7)
        assert g["matched_bucket_s"] == 600
        assert g["matched_bucket_start"] == 1_757_100_000.0

    def test_the_unmatched_quotient_is_never_published(self):
        g = adherence(**self.BASE, matched_emitted=15, matched_delivered=7)
        # The blocked version's fields. Their absence is the repair: there is no
        # longer an emission RATE on the row for anything to divide the 24h
        # delivery rate by.
        forbidden = {"emitted", "emitted_window_s", "emitted_rate",
                     "undelivered_fires", "emitted_minus_delivered"}
        assert forbidden.isdisjoint(g)


class TestTheAttributionComesFromTheBucketNotTheVerdict:
    """CERT-1969: the causal SENTENCE must be matched too, not just the counts.

    The first repair fixed the quotient — matched buckets, no pre-deploy history
    — and then still drove the sentence off the 24h `behind` verdict. Any row
    behind over a day whose bucket fraction was non-material printed *"the
    shortfall is at the SCHEDULER — the messages were never published"*. The
    block's reproduction: 15 published and 15 delivered against 15 expected is a
    perfectly healthy cohort, and that row accused the scheduler.

    A 24h shortfall beside a healthy 600s bucket is an ORDINARY state — it is
    what a rail that was just fixed looks like — so "not in this window" has to
    be an answer the instrument can give.
    """

    #: 40s interval, 600s bucket -> 15 fires expected per bucket. The 24h
    #: counters are `behind` (1080 of 2160) on every row here, deliberately:
    #: that is the verdict whose sentence used to leak into the attribution.
    BEHIND_24H = dict(
        starts=1080, starts_window_s=86400.0,
        deliveries=1080, deliveries_window_s=86400.0,
        interval_s=40.0, terminals=1079,
        matched_bucket_s=600, matched_bucket_start=1_757_100_000.0,
    )

    def test_a_healthy_bucket_under_a_behind_verdict_accuses_nobody(self):
        g = adherence(**self.BEHIND_24H, matched_emitted=15, matched_delivered=15)
        assert g["verdict"] == "behind"          # the 24h shortfall is real
        assert g["undelivered_fraction"] == 0.0
        assert g["bucket_attribution"] == "current_bucket_healthy"
        assert "SCHEDULER" not in g["reason"]
        assert "never reached a worker" not in g["reason"]
        assert "this window is healthy" in g["reason"]
        assert "predates it" in g["reason"]

    def test_short_publication_with_full_delivery_is_the_scheduler(self):
        # The bus's second worked example: 7 of 15 expected published, 7 of 7
        # delivered.
        g = adherence(**self.BEHIND_24H, matched_emitted=7, matched_delivered=7)
        assert g["bucket_attribution"] == "scheduler"
        assert "never published" in g["reason"]

    def test_full_publication_with_short_delivery_is_the_broker(self):
        # The third: 15 of 15 published, 7 delivered.
        g = adherence(**self.BEHIND_24H, matched_emitted=15, matched_delivered=7)
        assert g["bucket_attribution"] == "broker_or_worker"
        assert "never reached a worker" in g["reason"]

    def test_short_at_both_ends_says_both(self):
        g = adherence(**self.BEHIND_24H, matched_emitted=7, matched_delivered=3)
        assert g["bucket_attribution"] == "both"
        assert "BOTH ends" in g["reason"]

    def test_the_three_shapes_are_distinguishable_from_each_other(self):
        # The control. Every input outside the matched pair is identical, so
        # nothing but the bucket can be producing three different attributions.
        rows = {
            adherence(**self.BEHIND_24H, matched_emitted=e, matched_delivered=d)[
                "bucket_attribution"]
            for e, d in ((15, 15), (7, 7), (15, 7), (7, 3))
        }
        assert rows == {"current_bucket_healthy", "scheduler",
                        "broker_or_worker", "both"}

    def test_the_24h_counters_cannot_move_the_attribution(self):
        # The same requirement CERT-1966 imposed on the fraction, now on the
        # sentence: sweep the aggregate history and the attribution must not
        # move. This is the assertion that fails if the sentence is ever wired
        # back to `ratio`.
        seen = set()
        for deliveries in (0, 500, 1080, 2160, 4000):
            for window in (600.0, 86400.0):
                g = adherence(**{**self.BEHIND_24H, "deliveries": deliveries,
                                 "deliveries_window_s": window},
                              matched_emitted=15, matched_delivered=15)
                seen.add(g["bucket_attribution"])
        assert seen == {"current_bucket_healthy"}

    def test_an_on_schedule_row_still_carries_the_attribution(self):
        # Reported on every row, not only where a verdict wanted a sentence. A
        # healthy 24h ratio hiding a broken current bucket is #3276's shape
        # exactly, and it is the one this field can see first.
        g = adherence(
            starts=2160, starts_window_s=86400.0,
            deliveries=2160, deliveries_window_s=86400.0,
            interval_s=40.0, terminals=2160,
            matched_emitted=15, matched_delivered=7,
            matched_bucket_s=600, matched_bucket_start=1.0,
        )
        assert g["verdict"] == "on_schedule"
        assert g["bucket_attribution"] == "broker_or_worker"

    def test_attribution_is_refused_when_the_bucket_cannot_grade(self):
        from app.utils.schedule_adherence import MIN_EXPECTED_FIRES
        # Unknown delivery half.
        assert adherence(**self.BEHIND_24H, matched_emitted=15,
                         matched_delivered=None)["bucket_attribution"] is None
        # No bucket at all.
        assert adherence(**self.BEHIND_24H)["bucket_attribution"] is None
        # Too few publications to say anything.
        assert adherence(**self.BEHIND_24H, matched_emitted=1,
                         matched_delivered=0)["bucket_attribution"] is None
        # A beat so slow the BUCKET cannot hold `MIN_EXPECTED_FIRES` of it. The
        # bucket's own expectation is then under the refusal line, and grading
        # "published 2 of 0.2 scheduled" would be arithmetic, not evidence.
        slow = adherence(**{**self.BEHIND_24H, "interval_s": 3600.0},
                         matched_emitted=2, matched_delivered=2)
        assert 600 / 3600.0 < MIN_EXPECTED_FIRES
        assert slow["bucket_attribution"] is None

    def test_it_is_on_every_row_whatever_graded_it(self):
        rows = [
            adherence(starts=0, starts_window_s=None, interval_s=None),
            adherence(starts=1, starts_window_s=10.0, interval_s=40.0),
            adherence(starts=0, starts_window_s=None, interval_s=86400.0,
                      newest_start_age_s=10.0, counter_ttl_s=86400.0),
            adherence(**self.BEHIND_24H, matched_emitted=15, matched_delivered=7),
        ]
        for row in rows:
            assert "bucket_attribution" in row


class TestLeaseDeclinesAreTheirOwnNumber:
    """LAT-P238 ITEM 3, on lane1b's spec: the lease gate's share, published.

    ``self_gated_fires`` is ``max(0, deliveries - starts)`` — everything that
    drops between ``task_prerun`` and ``_tracked_run``. On ``poll_all_odds``
    that is TWO gates in series: ``single_flight``'s lease, then
    ``should_poll_now()``'s cadence check. So the difference is a SUPERSET of
    the lease declines, not a synonym for them, and one number cannot answer
    which gate is doing the declining.

    Published side by side, the cadence gate's share is readable by
    subtraction. Folded together, neither number means anything — the same
    argument that makes ``deliveries`` and ``starts`` two fields instead of one.
    """

    #: 30s beat, 24h window, 2880 scheduled. 2880 delivered, 1400 started:
    #: 1480 fires dropped between delivery and the body, of which 900 were the
    #: lease and (by subtraction) 580 were the cadence gate.
    TWO_GATES = dict(
        starts=1400, starts_window_s=86400.0,
        deliveries=2880, deliveries_window_s=86400.0,
        interval_s=30.0, terminals=1400,
        lease_declines=900, lease_declines_window_s=86400.0,
    )

    def test_the_two_gates_are_separable(self):
        g = adherence(**self.TWO_GATES)
        assert g["self_gated_fires"] == 1480
        assert g["lease_declines"] == 900
        # The whole point: the reader can now name the other gate's share.
        assert g["self_gated_fires"] - g["lease_declines"] == 580

    def test_declines_are_never_folded_into_self_gated_fires(self):
        without = adherence(**{k: v for k, v in self.TWO_GATES.items()
                               if not k.startswith("lease_declines")})
        for declines in (0, 900, 99_999):
            g = adherence(**{**self.TWO_GATES, "lease_declines": declines})
            assert g["self_gated_fires"] == without["self_gated_fires"], declines
            assert g["self_gate_fraction"] == without["self_gate_fraction"], declines

    def test_declines_are_never_a_numerator_and_never_a_verdict(self):
        # A tick that found the lease held WAS delivered and DID run. The beat
        # was perfect; grading on this would report a healthy scheduler as a
        # failing one.
        without = adherence(**{k: v for k, v in self.TWO_GATES.items()
                               if not k.startswith("lease_declines")})
        for declines in (0, 900, 99_999):
            g = adherence(**{**self.TWO_GATES, "lease_declines": declines})
            assert g["ratio"] == without["ratio"], declines
            assert g["verdict"] == without["verdict"], declines
            assert g["numerator"] == without["numerator"], declines
            assert g["reason"] == without["reason"], declines

    def test_the_count_carries_its_own_window(self):
        # A count without its age is not a rate: 346 declines is 346 in eight
        # minutes or 346 in twenty-four hours, and the payload has to say which.
        # This counter's window was previously unreadable because the only
        # surface exposing it (`/api/admin/redis-read`) returns the value alone.
        g = adherence(**self.TWO_GATES)
        assert g["lease_declines_window_s"] == 86400.0
        # And it is its OWN window, not borrowed from a neighbour that happens
        # to be on the row. A tumbling counter that rolled ten minutes ago has a
        # 600s window beside a 24h delivery counter, and reading the wrong one
        # inflates the rate by 144x.
        g2 = adherence(**{**self.TWO_GATES, "lease_declines_window_s": 600.0})
        assert g2["lease_declines_window_s"] == 600.0
        assert g2["window_s"] == 86400.0
        assert g2["deliveries_window_s"] == 86400.0

    def test_an_unmeasurable_window_still_publishes_the_count(self):
        # Unlike `undelivered_fraction`, nothing here is DERIVED, so an unknown
        # window suppresses no arithmetic — it is simply reported as unknown
        # beside a count that is still a fact. Dropping the count would lose a
        # real observation to protect a division that is not being done.
        g = adherence(**{**self.TWO_GATES, "lease_declines_window_s": None})
        assert g["lease_declines"] == 900
        assert g["lease_declines_window_s"] is None

    def test_both_fields_are_on_every_row_whatever_graded_it(self):
        rows = [
            adherence(starts=0, starts_window_s=None, interval_s=None),
            adherence(starts=1, starts_window_s=10.0, interval_s=40.0),
            adherence(starts=0, starts_window_s=None, interval_s=86400.0,
                      newest_start_age_s=10.0, counter_ttl_s=86400.0),
            adherence(**self.TWO_GATES),
        ]
        for row in rows:
            assert "lease_declines" in row
            assert "lease_declines_window_s" in row

    def test_no_lease_counter_is_unknown_not_zero(self):
        # Most tasks never take a lease at all. `None` says "this task has no
        # lease counter"; a 0 would claim it takes one and never declines,
        # which is a different and unsupported statement.
        g = adherence(starts=10, starts_window_s=3600.0, interval_s=30.0)
        assert g["lease_declines"] is None
        assert g["lease_declines_window_s"] is None
