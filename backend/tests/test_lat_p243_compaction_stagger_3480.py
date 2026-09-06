"""LAT-P243 (#3480) — two long-hold beats may not be resident on `background` at once.

THE SHIP THIS GUARDS: the search box stops going cold every morning.

`worker-background` is Standard-1X `--concurrency=2`. Six of its beats declare a
soft_time_limit of half an hour or more, and before this change five of them
could be resident simultaneously — enumerated, not eyeballed, 168 overlapping
window-pairs in any 7-day span, worst case SIX residents at 06:55Z against two
slots. `warm-typeahead` fires onto that same pool every 10s with `expires: 120`,
so through the outage every fire was discarded unstarted, the 65s response TTL
lapsed, and the head of the search box went cold.

WHY THE GUARD IS SHAPED THIS WAY, because the obvious shape rots on first
contact:

*   It transcribes NO time. Both the beat set and the windows are re-derived
    from the live `celery_app.conf.beat_schedule` and each task's DECLARED
    `soft_time_limit`. A guard holding a copy of the table would pass forever
    after someone edits the schedule, which is the exact edit it exists to
    catch.
*   It is DERIVED BY THRESHOLD, not by name. A new background beat that declares
    a long hold is covered the moment it is added, without anyone remembering
    this file.
*   The window is the DECLARED limit, never a sampled duration. The soft limit
    is the longest the system PERMITS the task to hold the slot; a bound taken
    from a measured maximum has been refuted twice in this program by the next
    sample.

NON-VACUITY IS TESTED, NOT ASSERTED. A checker that returns "no overlaps" because
it enumerates nothing would pass every assertion here about the live schedule.
So `TestTheDetectorIsNotVacuous` feeds it the exact PARENT schedule — the five
crontabs as they stood at `e34a6ce8` — and requires it to find them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from celery.schedules import crontab

from app.tasks import celery_app
from app.utils.schedule_adherence import (
    LONG_HOLD_SOFT_LIMIT_S,
    beat_queues,
    crontab_fire_times,
    long_hold_beats,
    residency_overlaps,
)

# Fixed anchors. Gotcha #44: the anchor is offset from a literal, never from the
# clock, and several are swept so a schedule restricted by day-of-week or
# day-of-month cannot pass by landing in a quiet week.
ANCHORS = [
    datetime(2026, 1, 5, tzinfo=timezone.utc),
    datetime(2026, 2, 26, tzinfo=timezone.utc),
    datetime(2026, 6, 1, tzinfo=timezone.utc),
    datetime(2026, 9, 7, tzinfo=timezone.utc),
    datetime(2026, 12, 28, tzinfo=timezone.utc),
]

# The parent schedule, copied verbatim from `app/tasks/__init__.py` at e34a6ce8.
# This is the ONLY place a literal time appears in this file, and it is here to
# be REFUTED rather than relied on.
PARENT_SCHEDULE_AT_e34a6ce8 = {
    "collapse-odds-snapshots-daily": crontab(minute=30, hour=6),
    "collapse-winprob-snapshots-daily": crontab(minute=35, hour=6),
    "collapse-futures-snapshots-daily": crontab(minute=40, hour=6),
    "turbo-collapse-futures": crontab(minute=30, hour="*/6"),
    "turbo-collapse-odds": crontab(minute=45, hour="*/6"),
}


def _live():
    """(beat_schedule, soft_limits, queues) read off the app that is actually loaded."""
    bs = celery_app.conf.beat_schedule
    queues = beat_queues(bs, celery_app.conf.task_routes, celery_app.conf.task_default_queue)
    softs = {
        name: (getattr(task, "soft_time_limit", None) or 0)
        for name, task in celery_app.tasks.items()
    }
    return bs, softs, queues


class TestTheLiveScheduleHasNoCoResidency:
    @pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: a.strftime("%Y-%m-%d"))
    def test_no_two_long_hold_background_beats_overlap(self, anchor):
        bs, softs, queues = _live()
        overlaps, unenumerable = residency_overlaps(bs, softs, queues, start=anchor, days=7)
        assert unenumerable == [], (
            "a long-hold background beat has a schedule this check cannot enumerate, "
            f"so it is an unmeasured hole rather than a pass: {unenumerable}"
        )
        assert overlaps == [], (
            "two long-hold beats can hold both `background` slots at once, which is a "
            "scheduled outage for every other beat on that pool — including "
            "`warm-typeahead`, whose fires expire after 120s and take the search box "
            "cold with them. Move one clear of the other, route it to `heavy`, or "
            "declare a shorter soft_time_limit.\nFirst 5 of "
            f"{len(overlaps)}:\n" + "\n".join(str(o) for o in overlaps[:5])
        )

    def test_the_check_covers_a_real_and_named_population(self):
        """A guard over an empty set passes trivially. Name what it is guarding."""
        bs, softs, queues = _live()
        names = long_hold_beats(bs, softs, queues)
        assert len(names) >= 6, f"expected the known long-hold background beats, got {names}"
        for expected in (
            "turbo-collapse-futures",
            "turbo-collapse-odds",
            "collapse-odds-snapshots-daily",
            "collapse-winprob-snapshots-daily",
            "collapse-futures-snapshots-daily",
            "precompute-bookmaker-calibration",
        ):
            assert expected in names, f"{expected} dropped out of the guarded set"

    def test_every_guarded_beat_actually_fires_in_the_window(self):
        """`residency_overlaps` cannot find an overlap between beats that never
        fire. If a schedule silently enumerated to zero fires the suite above
        would be green and meaningless."""
        bs, softs, queues = _live()
        for name in long_hold_beats(bs, softs, queues):
            fires = crontab_fire_times(bs[name]["schedule"], ANCHORS[3], 7)
            assert fires, f"{name} enumerated to no fires in a 7-day window"


class TestTheDetectorIsNotVacuous:
    """Feed it the schedule this change replaced and require it to object."""

    @pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: a.strftime("%Y-%m-%d"))
    def test_the_parent_schedule_is_caught(self, anchor):
        bs, softs, queues = _live()
        parent = dict(bs)
        for name, sched in PARENT_SCHEDULE_AT_e34a6ce8.items():
            parent[name] = {**bs[name], "schedule": sched}
        overlaps, unenumerable = residency_overlaps(parent, softs, queues, start=anchor, days=7)
        assert unenumerable == []
        assert len(overlaps) >= 100, (
            "the parent schedule collided 168 pair-times per week; a detector that "
            f"finds only {len(overlaps)} is not reading it"
        )
        pairs = {tuple(sorted((o["a"], o["b"]))) for o in overlaps}
        # The pair the codebase's own comment predicted, and never enforced.
        assert ("turbo-collapse-futures", "turbo-collapse-odds") in pairs
        # The five-way morning pile-up.
        assert ("collapse-odds-snapshots-daily", "turbo-collapse-futures") in pairs
        assert ("collapse-futures-snapshots-daily", "turbo-collapse-odds") in pairs

    def test_the_parent_put_six_grinders_on_a_two_slot_pool(self):
        """The pair count alone understates it: count SIMULTANEOUS residents."""
        bs, softs, queues = _live()
        parent = dict(bs)
        for name, sched in PARENT_SCHEDULE_AT_e34a6ce8.items():
            parent[name] = {**bs[name], "schedule": sched}
        windows = []
        for name in long_hold_beats(parent, softs, queues):
            hold = timedelta(seconds=softs[parent[name]["task"]])
            for f in crontab_fire_times(parent[name]["schedule"], ANCHORS[3], 2):
                windows.append((f, f + hold, name))
        worst = max(
            len([m for (s2, e2, m) in windows if s2 <= s < e2]) for (s, _e, _n) in windows
        )
        assert worst >= 6, f"expected the six-deep 06:55Z pile-up on the parent, got {worst}"

    def test_an_injected_overlap_is_caught(self):
        """Independent of the parent: two synthetic beats one minute apart."""
        bs = {
            "grinder-a": {"task": "t.a", "schedule": crontab(minute=0, hour=3),
                          "options": {"queue": "background"}},
            "grinder-b": {"task": "t.b", "schedule": crontab(minute=1, hour=3),
                          "options": {"queue": "background"}},
        }
        softs = {"t.a": 1800, "t.b": 1800}
        queues = {"t.a": ["background"], "t.b": ["background"]}
        overlaps, _ = residency_overlaps(bs, softs, queues, start=ANCHORS[3], days=2)
        assert len(overlaps) == 2, overlaps
        assert overlaps[0]["overlap_s"] == pytest.approx(1740.0)


class TestTheDerivationItself:
    def test_a_short_beat_is_out_of_scope_and_a_long_one_is_in(self):
        bs = {
            "short": {"task": "t.short", "schedule": crontab(minute=0),
                      "options": {"queue": "background"}},
            "long": {"task": "t.long", "schedule": crontab(minute=0),
                     "options": {"queue": "background"}},
        }
        softs = {"t.short": LONG_HOLD_SOFT_LIMIT_S - 1, "t.long": LONG_HOLD_SOFT_LIMIT_S}
        queues = {"t.short": ["background"], "t.long": ["background"]}
        assert long_hold_beats(bs, softs, queues) == ["long"]

    def test_a_long_hold_on_another_queue_is_out_of_scope(self):
        """`heavy` has its own slots. This check is about `background`'s two."""
        bs = {"h": {"task": "t.h", "schedule": crontab(minute=0),
                    "options": {"queue": "heavy"}}}
        assert long_hold_beats(bs, {"t.h": 3600}, {"t.h": ["heavy"]}) == []
        assert long_hold_beats(bs, {"t.h": 3600}, {"t.h": ["heavy"]}, queue="heavy") == ["h"]

    def test_a_task_with_entries_on_two_queues_counts_for_background(self):
        """`beat_queues` returns a LIST because entries need not agree. One
        entry on the pool is enough to hold one of its slots."""
        bs = {"x": {"task": "t.x", "schedule": crontab(minute=0)}}
        assert long_hold_beats(bs, {"t.x": 3600}, {"t.x": ["background", "heavy"]}) == ["x"]

    def test_star_slash_six_expands_to_four_fires_a_day(self):
        """Read from celery's own parsed field set, so the '*/6' string itself
        is never re-parsed here."""
        fires = crontab_fire_times(crontab(minute=30, hour="*/6"), ANCHORS[3], 1)
        assert [f.strftime("%H:%M") for f in fires] == ["00:30", "06:30", "12:30", "18:30"]

    def test_a_weekly_schedule_fires_once_a_week_on_the_right_day(self):
        """celery's day_of_week is 0=Sunday; python's weekday() is 0=Monday, and
        getting that conversion backwards would shift every weekly beat by a day."""
        fires = crontab_fire_times(crontab(minute=0, hour=4, day_of_week=1), ANCHORS[3], 14)
        assert len(fires) == 2
        for f in fires:
            assert f.strftime("%A") == "Monday"

    def test_a_plain_interval_schedule_enumerates(self):
        fires = crontab_fire_times(600.0, ANCHORS[3], 1)
        assert len(fires) == 144
        assert fires[1] - fires[0] == timedelta(seconds=600)

    def test_a_timedelta_schedule_enumerates(self):
        fires = crontab_fire_times(timedelta(minutes=10), ANCHORS[3], 1)
        assert len(fires) == 144

    def test_an_unreadable_schedule_returns_none_not_an_empty_list(self):
        """The distinction is the whole point: `[]` reads as 'never overlaps',
        which is the one answer that is certainly wrong for a beat nobody can
        enumerate. `None` is reported as a hole by `residency_overlaps`."""
        assert crontab_fire_times(object(), ANCHORS[3], 1) is None
        assert crontab_fire_times(None, ANCHORS[3], 1) is None
        assert crontab_fire_times(0, ANCHORS[3], 1) is None
        assert crontab_fire_times(True, ANCHORS[3], 1) is None

    def test_an_unenumerable_long_hold_beat_is_reported_not_swallowed(self):
        bs = {"weird": {"task": "t.w", "schedule": object(),
                        "options": {"queue": "background"}}}
        overlaps, unenumerable = residency_overlaps(
            bs, {"t.w": 3600}, {"t.w": ["background"]}, start=ANCHORS[3], days=1
        )
        assert overlaps == []
        assert unenumerable == ["weird"]

    def test_touching_windows_do_not_count_as_overlapping(self):
        """B firing exactly as A's declared limit expires is legal — it is the
        tightest schedule the rule permits, and an off-by-one here would make
        the guard unsatisfiable."""
        bs = {
            "a": {"task": "t.a", "schedule": crontab(minute=0, hour=3),
                  "options": {"queue": "background"}},
            "b": {"task": "t.b", "schedule": crontab(minute=30, hour=3),
                  "options": {"queue": "background"}},
        }
        overlaps, _ = residency_overlaps(
            bs, {"t.a": 1800, "t.b": 1800}, {"t.a": ["background"], "t.b": ["background"]},
            start=ANCHORS[3], days=1,
        )
        assert overlaps == []


class TestTheStaggerKeepsWhatItWasNotAskedToChange:
    """A reschedule must not quietly become a rate change or a requeue."""

    EXPECTED_CADENCE_S = {
        "collapse-odds-snapshots-daily": 86400,
        "collapse-winprob-snapshots-daily": 86400,
        "collapse-futures-snapshots-daily": 86400,
        "turbo-collapse-futures": 21600,
        "turbo-collapse-odds": 21600,
    }

    def test_each_moved_beat_fires_exactly_as_often_as_before(self):
        bs = celery_app.conf.beat_schedule
        for name, cadence in self.EXPECTED_CADENCE_S.items():
            fires = crontab_fire_times(bs[name]["schedule"], ANCHORS[3], 7)
            assert len(fires) == 7 * 86400 // cadence, (
                f"{name} changed rate: {len(fires)} fires in 7 days"
            )

    def test_the_moved_beats_still_land_on_background(self):
        bs = celery_app.conf.beat_schedule
        queues = beat_queues(bs, celery_app.conf.task_routes, celery_app.conf.task_default_queue)
        for name in self.EXPECTED_CADENCE_S:
            assert queues[bs[name]["task"]] == ["background"]

    def test_the_calibration_lanes_beat_did_not_move(self):
        """`precompute-bookmaker-calibration` is scheduled AROUND, never moved:
        its :55 slot is load-bearing for the hourly `precompute-calibration-main`
        (:15) that consumes its key, and the file it lives in is the calibration
        lane's under D45."""
        sched = celery_app.conf.beat_schedule["precompute-bookmaker-calibration"]["schedule"]
        assert sorted(sched.minute) == [55]
        assert sorted(sched.hour) == [0, 6, 12, 18]

    def test_the_collapse_kwargs_are_untouched(self):
        bs = celery_app.conf.beat_schedule
        assert bs["collapse-odds-snapshots-daily"]["kwargs"] == {"table": "odds", "limit": 500}
        assert bs["collapse-winprob-snapshots-daily"]["kwargs"] == {"table": "winprob", "limit": 500}
        assert bs["collapse-futures-snapshots-daily"]["kwargs"] == {"table": "futures", "limit": 500}
        assert bs["turbo-collapse-futures"]["kwargs"] == {"limit": 5000}
        assert bs["turbo-collapse-odds"]["kwargs"] == {"limit": 5000}
