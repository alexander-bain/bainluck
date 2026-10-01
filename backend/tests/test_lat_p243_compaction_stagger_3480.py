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
    QUEUE_SLOTS,
    beat_queues,
    crontab_fire_times,
    effective_hold_s,
    fire_isolation_violations,
    long_hold_beats,
    queues_that_cannot_guarantee_a_slot,
    residency_overlaps,
    unbudgeted_residents,
    warmer_expiry_budget_s,
)

#: The beats this ship placed. The isolation rule is about where THESE arrive.
COMPACTION_SUBJECTS = frozenset({
    "turbo-collapse-futures",
    "turbo-collapse-odds",
    "collapse-odds-snapshots-daily",
    "collapse-winprob-snapshots-daily",
    "collapse-futures-snapshots-daily",
})

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
# The schedule CERT-2045 BLOCKED, copied verbatim from `22bed49c`. Like the
# parent above, it is here to be REFUTED. Its defect is NOT a pairwise long-hold
# overlap — it has none — so `residency_overlaps` passes it and only the
# budget-derived isolation rule can see it. That is the whole point of the repair.
BLOCKED_SCHEDULE_AT_22bed49c = {
    "collapse-odds-snapshots-daily": crontab(minute=40, hour=4),
    "collapse-winprob-snapshots-daily": crontab(minute=15, hour=5),
    "collapse-futures-snapshots-daily": crontab(minute=50, hour=5),
    "turbo-collapse-futures": crontab(minute=40, hour="1,7,13,19"),
    "turbo-collapse-odds": crontab(minute=30, hour="3,9,15,21"),
}

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
        entry on the pool is enough to hold one of its slots — wherever in the
        list it appears. `beat_queues` happens to sort, and "background" happens
        to sort first among this repo's three queue names, so a membership test
        written as "is it the FIRST entry" would pass today and break the day a
        queue named earlier in the alphabet is added."""
        bs = {"x": {"task": "t.x", "schedule": crontab(minute=0)}}
        assert long_hold_beats(bs, {"t.x": 3600}, {"t.x": ["background", "heavy"]}) == ["x"]
        assert long_hold_beats(bs, {"t.x": 3600}, {"t.x": ["heavy", "background"]}) == ["x"]
        assert long_hold_beats(bs, {"t.x": 3600}, {"t.x": ["alpha", "heavy"]}) == []

    def test_the_overlap_span_is_the_shorter_windows_share_not_the_longer_one(self):
        """A 10-minute beat landing inside a 1-hour grinder's window overlaps for
        TEN minutes, not for the fifty that remain of the grinder. Reporting the
        longer side would make every small collision look like a total outage
        and rank the work-list wrong."""
        bs = {
            "grinder": {"task": "t.long", "schedule": crontab(minute=0, hour=3),
                        "options": {"queue": "background"}},
            "shortish": {"task": "t.short", "schedule": crontab(minute=10, hour=3),
                         "options": {"queue": "background"}},
        }
        overlaps, _ = residency_overlaps(
            bs, {"t.long": 3600, "t.short": 1200},
            {"t.long": ["background"], "t.short": ["background"]},
            start=ANCHORS[3], days=1,
        )
        assert len(overlaps) == 1, overlaps
        # `shortish` runs 03:10-03:30 entirely inside `grinder`'s 03:00-04:00.
        assert overlaps[0]["overlap_s"] == pytest.approx(1200.0)

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


class TestNoCompactionBeatArrivesBesideOtherLongWork:
    """CERT-2045's repair. The invariant is derived from the warmer's own expiry
    budget, not from a round number, and it does not require both sides to be
    long — a 540s task exhausts a slot exactly as thoroughly as a 3600s one."""

    @pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: a.strftime("%Y-%m-%d"))
    def test_the_live_schedule_has_no_simultaneous_arrivals(self, anchor):
        bs, softs, queues = _live()
        violations, unenumerable = fire_isolation_violations(
            bs, softs, queues, COMPACTION_SUBJECTS, start=anchor, days=7
        )
        assert unenumerable == [], unenumerable
        assert violations == [], (
            "a compaction beat fires within `warm-typeahead`'s expiry budget of "
            "other long-holding background work. Three arrivals on a two-slot pool "
            "means two of them take both slots and the warmer's message dies behind "
            "them.\nFirst 5 of "
            f"{len(violations)}:\n" + "\n".join(str(v) for v in violations[:5])
        )

    def test_the_budget_is_read_from_the_warmer_not_typed(self):
        """If this ever returns a default, the isolation check goes vacuous — and
        a vacuous check on this exact property is what CERT-2045 caught."""
        bs, _softs, _queues = _live()
        assert warmer_expiry_budget_s(bs) == 120.0
        assert bs["warm-typeahead"]["options"]["expires"] == 120

    def test_a_missing_or_zero_budget_raises_rather_than_defaulting(self):
        with pytest.raises(KeyError):
            warmer_expiry_budget_s({})
        with pytest.raises(ValueError):
            warmer_expiry_budget_s({"warm-typeahead": {"options": {}}})
        with pytest.raises(ValueError):
            warmer_expiry_budget_s({"warm-typeahead": {"options": {"expires": 0}}})


class TestTheRepairIsNotVacuous:
    """CERT-2045's required regression, in its own words: the real 05:15 triple
    must FAIL on the blocked sha and PASS after repair."""

    def _blocked(self):
        bs, softs, queues = _live()
        blocked = dict(bs)
        for name, sched in BLOCKED_SCHEDULE_AT_22bed49c.items():
            blocked[name] = {**bs[name], "schedule": sched}
        return blocked, softs, queues

    @pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: a.strftime("%Y-%m-%d"))
    def test_the_blocked_schedule_is_caught(self, anchor):
        blocked, softs, queues = self._blocked()
        violations, unenumerable = fire_isolation_violations(
            blocked, softs, queues, COMPACTION_SUBJECTS, start=anchor, days=7
        )
        assert unenumerable == []
        assert len(violations) >= 300, (
            f"the blocked schedule collided 364 arrival-pairs per week; {len(violations)} "
            "means the detector is not reading it"
        )

    def test_the_exact_triple_cert_2045_named_is_caught(self):
        """Not "some violation" — the named one. `collapse-winprob-snapshots-daily`
        at 05:15Z against `backfill-kalshi-trade-history` (600s) and
        `poll-polymarket-hourly` (540s), both at zero separation."""
        blocked, softs, queues = self._blocked()
        violations, _ = fire_isolation_violations(
            blocked, softs, queues, COMPACTION_SUBJECTS, start=ANCHORS[3], days=1
        )
        triple = {
            (v["competitor"], v["competitor_declared_hold_s"], v["separation_s"])
            for v in violations
            if v["subject"] == "collapse-winprob-snapshots-daily"
            and v["subject_fire"][11:16] == "05:15"
        }
        assert ("backfill-kalshi-trade-history", 600, 0.0) in triple, triple
        assert ("poll-polymarket-hourly", 540, 0.0) in triple, triple

    def test_the_pairwise_check_alone_would_have_passed_the_blocked_schedule(self):
        """The reason the repair needed a SECOND invariant rather than a tweak to
        the first. If this ever fails, the two rules have collapsed into one and
        the isolation rule is no longer earning its place."""
        blocked, softs, queues = self._blocked()
        overlaps, unenumerable = residency_overlaps(
            blocked, softs, queues, start=ANCHORS[3], days=7
        )
        assert unenumerable == []
        assert overlaps == [], (
            "the blocked schedule was pairwise-clean — that is why CERT-2045's "
            "case slipped through it"
        )

    @pytest.mark.parametrize(
        "competitor_minute,expected",
        [(0, 1), (1, 1), (2, 0), (5, 0)],
        ids=["same-instant", "60s-apart", "120s-apart-exactly", "300s-apart"],
    )
    def test_the_budget_boundary_is_a_bound_and_not_a_vibe(self, competitor_minute, expected):
        """Inside the budget violates; exactly at it does not. Crontab
        granularity is one minute, which is also the real domain — the schedule
        cannot express a 119-second offset, so pinning one would be pinning
        arithmetic the system can never produce. 120s is the budget, so two
        minutes clear is the tightest legal placement, and a rule that rejected
        it would be unsatisfiable rather than strict."""
        bs = {
            "warm-typeahead": {"task": "t.warm", "schedule": 10.0,
                               "options": {"queue": "background", "expires": 120}},
            "subject": {"task": "t.sub", "schedule": crontab(minute=0, hour=3),
                        "options": {"queue": "background"}},
            "comp": {"task": "t.comp",
                     "schedule": crontab(minute=competitor_minute, hour=3),
                     "options": {"queue": "background"}},
        }
        softs = {"t.warm": 100, "t.sub": 1700, "t.comp": 600}
        queues = {k: ["background"] for k in ("t.warm", "t.sub", "t.comp")}
        violations, unenumerable = fire_isolation_violations(
            bs, softs, queues, {"subject"}, start=ANCHORS[3], days=1
        )
        assert unenumerable == [], unenumerable
        assert len(violations) == expected, (competitor_minute, violations)

    def test_a_short_competitor_is_not_a_violation_however_close(self):
        """A beat that gives its slot back inside the budget is not the problem —
        including one that fires at the same instant. Without this the rule would
        forbid every arrival and be unsatisfiable."""
        bs = {
            "warm-typeahead": {"task": "t.warm", "schedule": 10.0,
                               "options": {"queue": "background", "expires": 120}},
            "subject": {"task": "t.sub", "schedule": crontab(minute=0, hour=3),
                        "options": {"queue": "background"}},
            "quick": {"task": "t.quick", "schedule": crontab(minute=0, hour=3),
                      "options": {"queue": "background"}},
        }
        softs = {"t.warm": 100, "t.sub": 1700, "t.quick": 120}
        queues = {k: ["background"] for k in ("t.warm", "t.sub", "t.quick")}
        violations, _ = fire_isolation_violations(
            bs, softs, queues, {"subject"}, start=ANCHORS[3], days=1
        )
        assert violations == []

    def test_a_long_competitor_on_another_queue_is_not_a_violation(self):
        bs = {
            "warm-typeahead": {"task": "t.warm", "schedule": 10.0,
                               "options": {"queue": "background", "expires": 120}},
            "subject": {"task": "t.sub", "schedule": crontab(minute=0, hour=3),
                        "options": {"queue": "background"}},
            "heavyguy": {"task": "t.h", "schedule": crontab(minute=0, hour=3),
                         "options": {"queue": "heavy"}},
        }
        softs = {"t.warm": 100, "t.sub": 1700, "t.h": 3600}
        queues = {"t.warm": ["background"], "t.sub": ["background"], "t.h": ["heavy"]}
        violations, _ = fire_isolation_violations(
            bs, softs, queues, {"subject"}, start=ANCHORS[3], days=1
        )
        assert violations == []

    def test_an_unenumerable_competitor_is_reported_not_swallowed(self):
        bs = {
            "warm-typeahead": {"task": "t.warm", "schedule": 10.0,
                               "options": {"queue": "background", "expires": 120}},
            "subject": {"task": "t.sub", "schedule": crontab(minute=0, hour=3),
                        "options": {"queue": "background"}},
            "weird": {"task": "t.w", "schedule": object(),
                      "options": {"queue": "background"}},
        }
        softs = {"t.warm": 100, "t.sub": 1700, "t.w": 3600}
        queues = {k: ["background"] for k in ("t.warm", "t.sub", "t.w")}
        violations, unenumerable = fire_isolation_violations(
            bs, softs, queues, {"subject"}, start=ANCHORS[3], days=1
        )
        assert violations == []
        assert unenumerable == ["weird"]


class TestTheClaimThatIsolationIsTheOnlyRemainingPath:
    """The load-bearing claim in this ship's disclosure, made checkable.

    CERT-2045 asked for "a worker opportunity for `warm-typeahead` inside 120s
    THROUGHOUT every moved compaction window". That is not schedulable, and the
    ship says so rather than substituting a weaker invariant quietly. Prose
    claims rot; this asserts it.

    ⚠️ **THIS IS THE DECLARED UPPER BOUND, NOT MEASURED OCCUPANCY.** A declared
    soft limit is what a task says it MAY take; p95 is what it does take, and the
    two differ by a lot here — only six background tasks have a measured p95 over
    the budget, against 59 that declare one. The declared model is used because 78
    of 110 background tasks have no recorded duration at all, so it is the only
    number that covers the whole population. Anyone costing the dedicated worker
    should read measured pool occupancy instead; the declared bound overstates the
    case in the expensive direction.

    ⚠️ **IF THIS TEST FAILS, THAT IS GOOD NEWS AND THE SHIP SHOULD ACT ON IT.**
    It fails when a schedulable window HAS appeared — because beats were retired,
    moved to `heavy`, or given shorter soft limits — which would mean the
    throughout-the-window invariant became reachable and the dedicated-worker ask
    in `alex-inbox` can be withdrawn. Do not raise the bound to make it pass.
    """

    #: The shortest moved compaction window (`collapse_snapshots`, soft 1700s).
    #: A window this long must exist and be free before "throughout the window"
    #: could be satisfied by scheduling at all.
    SHORTEST_COMPACTION_WINDOW_MIN = 1700 // 60

    def _over_budget_windows(self, anchor):
        bs, softs, queues = _live()
        budget = warmer_expiry_budget_s(bs)
        out = []
        for name, entry in bs.items():
            task = entry.get("task")
            if not task or name in COMPACTION_SUBJECTS or name == "warm-typeahead":
                continue
            if "background" not in (queues.get(task) or []):
                continue
            hold = softs.get(task) or 0
            if hold <= budget:
                continue
            fires = crontab_fire_times(entry["schedule"], anchor, 1)
            if fires is None:
                continue
            for f in fires:
                out.append((f, f + timedelta(seconds=hold)))
        return out

    def test_no_free_window_long_enough_to_hold_a_compaction_pass_exists(self):
        anchor = ANCHORS[3]
        windows = self._over_budget_windows(anchor)
        assert windows, "nothing to measure — the population went empty, which is itself news"
        free_run = best = 0
        for m in range(1440):
            t = anchor + timedelta(minutes=m)
            if any(a <= t < b for a, b in windows):
                free_run = 0
            else:
                free_run += 1
                best = max(best, free_run)
        assert best < self.SHORTEST_COMPACTION_WINDOW_MIN, (
            f"a {best}-minute window free of over-budget background beats now exists, which "
            f"is longer than the shortest compaction pass ({self.SHORTEST_COMPACTION_WINDOW_MIN} "
            "min). The 'throughout the window' invariant may now be schedulable — reopen the "
            "dedicated-worker question in alex-inbox before raising this bound."
        )

    def test_the_population_is_large_enough_that_this_is_structural(self):
        """Not one awkward beat: a crowd. Stated as a floor so adding beats can
        never make it pass for the wrong reason."""
        bs, softs, queues = _live()
        budget = warmer_expiry_budget_s(bs)
        entries = [
            n for n, e in bs.items()
            if e.get("task")
            and n not in COMPACTION_SUBJECTS
            and n != "warm-typeahead"
            and "background" in (queues.get(e["task"]) or [])
            and (softs.get(e["task"]) or 0) > budget
        ]
        assert len(entries) >= 40, (
            f"only {len(entries)} background beats now declare a hold over the "
            f"{budget:.0f}s budget, down from 59. If this has genuinely shrunk, "
            "re-measure before trusting the disclosure that says isolation is the only path."
        )


class TestNoQueueWeAlreadyPayForIsAHomeForTheWarmer:
    """CERT-2053's other half: *"or another topology"*.

    CERT-2045 offered two ways out — schedule, or isolation. CERT-2053 accepted
    that the schedule half is exhausted and asked for the second: satisfy the
    full-window invariant "via real isolation/capacity or another topology".
    Before anyone buys a fourth worker, the three we already run have to be ruled
    out ON THE RECORD, and by a rule rather than by an opinion. That is this
    class. `TestTheClaimThatIsolationIsTheOnlyRemainingPath` above examines
    `background` alone and therefore could never have answered it.

    THE RULE, one sentence: a queue cannot be shown to give the warmer a slot
    inside its expiry budget if it has at least as many residents whose DECLARED
    hold exceeds that budget as it has slots. Every queue fails it today.

    ⚠️ THE ANSWER IS "CANNOT BE PROVEN TO WORK", NOT "IS PROVEN TO FAIL", and the
    difference is load-bearing when the conclusion is a purchase. See
    `queues_that_cannot_guarantee_a_slot`.

    ⚠️ IF THIS CLASS FAILS, THAT IS GOOD NEWS. A queue leaving the disqualified
    set means somewhere we already pay for might house the warmer, and the
    dedicated-worker ask in `alex-inbox` should be re-priced against a
    measurement of THAT queue before a dyno is bought.
    """

    def _inputs(self):
        bs, softs, queues = _live()
        return (bs, softs, queues, warmer_expiry_budget_s(bs),
                celery_app.conf.task_time_limit)

    def test_every_queue_that_exists_is_disqualified(self):
        bs, softs, queues, budget, hard = self._inputs()
        disqualified = queues_that_cannot_guarantee_a_slot(
            bs, softs, queues, budget_s=budget, global_hard_limit=hard)
        survivors = sorted(set(QUEUE_SLOTS) - set(disqualified))
        assert not survivors, (
            f"{survivors} can no longer be disqualified from housing `warm-typeahead` "
            f"on declarations alone. That is the good-news failure: MEASURE the "
            f"occupancy of {survivors} before spending on a fourth worker — a queue "
            "surviving this check has earned a measurement, not a move."
        )

    def test_realtime_is_disqualified_by_the_global_hard_limit_not_by_soft_limits(self):
        """The trap this ship nearly walked into, pinned so nobody walks into it.

        Nine of `realtime`'s ten beats declare NO `soft_time_limit`. Read that as
        `0` and realtime scores one over-budget resident against four slots — it
        clears, and looks like the free home that makes the dyno ask unnecessary.
        It is not: #3060 measured its four pollers at p95s of 111-260s against
        30-120s periods, ~9 slots of demand on 4, and the last beat placed there
        on exactly this reasoning completed 7.0% of its fires. The declarations
        agree once the global hard `task_time_limit` is read as the bound that an
        unset soft limit falls back to.
        """
        bs, softs, queues, budget, hard = self._inputs()
        assert hard and hard > budget, (
            f"the global task_time_limit is {hard!r}; this test's whole argument is "
            f"that it is the fallback bound and that it exceeds the {budget:.0f}s "
            "budget. If it changed, re-derive rather than adjust."
        )

        # The wrong reading, written out rather than described: `soft or 0`, so an
        # unset limit scores as a task that returns the slot instantly.
        naive = [
            n for n, e in bs.items()
            if e.get("task") and n != "warm-typeahead"
            and "realtime" in (queues.get(e["task"]) or [])
            and (softs.get(e["task"]) or 0) > budget
        ]
        assert len(naive) < QUEUE_SLOTS["realtime"], (
            f"this test asserts that the NAIVE reading clears realtime ({naive}), which "
            "is why the correct reading has to be spelled out. It no longer does, so "
            "the trap is gone and this test should be retired rather than repaired."
        )

        over, unbounded = unbudgeted_residents(
            bs, softs, queues, queue="realtime", budget_s=budget,
            global_hard_limit=hard)
        assert len(over) + len(unbounded) >= QUEUE_SLOTS["realtime"], (
            f"realtime now has only {len(over) + len(unbounded)} residents that cannot "
            f"be shown to release inside {budget:.0f}s, against "
            f"{QUEUE_SLOTS['realtime']} slots — it may be a home. Measure it."
        )

    def test_unset_soft_limit_is_read_as_the_global_bound_and_never_as_zero(self):
        assert effective_hold_s(None, 300) == 300.0
        assert effective_hold_s(0, 300) == 300.0
        assert effective_hold_s(90, 300) == 90.0, "a declared soft limit wins over the global"
        assert effective_hold_s(None, None) is None, "no bound at all is None, not 0"
        assert effective_hold_s(None, 0) is None

    def test_the_rule_clears_a_queue_that_genuinely_has_room(self):
        """Non-vacuity, and in the direction that matters: the disqualifier must
        be capable of saying NO. A checker that disqualifies everything would pass
        `test_every_queue_that_exists_is_disqualified` while meaning nothing."""
        bs = {
            "warm-typeahead": {"task": "app.tasks.warm_typeahead",
                               "options": {"expires": 120}},
            "short-a": {"task": "t.a"},
            "short-b": {"task": "t.b"},
            "grinder": {"task": "t.g"},
        }
        queues = {"app.tasks.warm_typeahead": ["spacious"], "t.a": ["spacious"],
                  "t.b": ["spacious"], "t.g": ["spacious"]}
        softs = {"t.a": 30, "t.b": 45, "t.g": 900}
        slots = {"spacious": 4}

        disqualified = queues_that_cannot_guarantee_a_slot(
            bs, softs, queues, budget_s=120, slots=slots, global_hard_limit=300)
        assert disqualified == {}, (
            "one grinder against four slots leaves three that provably return inside "
            f"the budget, so this queue must clear: {disqualified}")

        # ...and it must still fire when the same queue is narrowed to one slot.
        assert set(queues_that_cannot_guarantee_a_slot(
            bs, softs, queues, budget_s=120, slots={"spacious": 1},
            global_hard_limit=300)) == {"spacious"}

    def test_a_hold_of_exactly_the_budget_is_not_over_it(self):
        """The boundary, matching `fire_isolation_violations`' `<= budget: continue`.

        A resident that returns the slot at exactly the expiry instant has not
        exceeded the budget, and the two helpers must not disagree about the tie —
        one of them saying 120s is fine while the other says it is a violation is
        how a rule becomes two rules.
        """
        bs = {
            "warm-typeahead": {"task": "app.tasks.warm_typeahead",
                               "options": {"expires": 120}},
            "exactly-at-budget": {"task": "t.exact"},
            "one-second-over": {"task": "t.over"},
        }
        queues = {"app.tasks.warm_typeahead": ["q"], "t.exact": ["q"], "t.over": ["q"]}
        over, unbounded = unbudgeted_residents(
            bs, {"t.exact": 120, "t.over": 121}, queues,
            queue="q", budget_s=120, global_hard_limit=300)
        assert over == ["one-second-over"], over
        assert unbounded == []

    def test_a_resident_with_no_bound_of_any_kind_disqualifies_and_is_reported_apart(self):
        """The `unbounded` arm has no live examples — the global hard limit covers
        every task today — so without this it is dead code that the battery walks
        straight through. It is kept because the global limit is one config edit
        from being removed, and "no answer at all" must not silently fold into
        "300s, which is over budget": they are different findings.
        """
        bs = {
            "warm-typeahead": {"task": "app.tasks.warm_typeahead",
                               "options": {"expires": 120}},
            "no-bound-a": {"task": "t.a"},
            "no-bound-b": {"task": "t.b"},
        }
        queues = {"app.tasks.warm_typeahead": ["q"], "t.a": ["q"], "t.b": ["q"]}
        softs = {"t.a": 0, "t.b": None}

        over, unbounded = unbudgeted_residents(
            bs, softs, queues, queue="q", budget_s=120, global_hard_limit=None)
        assert over == [], "no declared hold is not an over-budget hold"
        assert unbounded == ["no-bound-a", "no-bound-b"]

        disqualified = queues_that_cannot_guarantee_a_slot(
            bs, softs, queues, budget_s=120, slots={"q": 2}, global_hard_limit=None)
        assert set(disqualified) == {"q"}, (
            "two residents with no bound at all against two slots must disqualify the "
            f"queue on the unbounded arm alone: {disqualified}")
        assert disqualified["q"]["unbounded"] == ["no-bound-a", "no-bound-b"]
        assert disqualified["q"]["over_budget"] == []

    def test_the_warmer_is_never_counted_as_its_own_competitor(self):
        """`warm-typeahead` declares soft 100s, under the budget, so it would not
        land in `over_budget` today anyway — which is exactly why the exclusion
        needs a test that does not depend on today's number."""
        bs = {
            "warm-typeahead": {"task": "app.tasks.warm_typeahead",
                               "options": {"expires": 120}},
            "other": {"task": "t.other"},
        }
        queues = {"app.tasks.warm_typeahead": ["q"], "t.other": ["q"]}
        # The warmer given an over-budget hold: it must STILL not be counted.
        over, unbounded = unbudgeted_residents(
            bs, {"app.tasks.warm_typeahead": 9999, "t.other": 900},
            queues, queue="q", budget_s=120, global_hard_limit=300)
        assert over == ["other"], over
        assert unbounded == []
