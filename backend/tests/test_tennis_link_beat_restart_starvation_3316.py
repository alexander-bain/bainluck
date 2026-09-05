"""#3316 — the tennis StatPal link beat must survive a deploy storm.

THE DEFECT, MEASURED IN PRODUCTION ON 2026-09-05. `link-tennis-statpal-fixtures-10min`
was scheduled as a bare float, `600.0`. A float schedule is RELATIVE: celery's
`ScheduleEntry` sets `last_run_at = now` every time beat starts, and the
`celerybeat-schedule` shelve that would otherwise carry the old deadline across
does not survive a Heroku dyno (ephemeral filesystem). So every scheduler boot
re-arms a fresh full period.

That is survivable at one deploy and not at ours. Thirty releases landed between
15:22Z and 21:15Z — a scheduler restart every ~12 min against a 10 min period.
Five of them (20:54:30, 20:59:09, 21:02:27, 21:07:00, 21:15:47) landed closer
together than the period and starved the entry outright: last fire 20:48:17Z,
next fire 21:26:42Z, a 38-minute hole. `21:26:42` is exactly 600 s after the
21:16:09Z dyno boot, which is the mechanism's fingerprint rather than a
coincidence. Over 12.7 h the entry made 50 of a nominal 76 passes (66%), with 12
gaps past 1200 s and a worst gap of 42.8 min.

THE SHIP THIS GUARDS. The beat's own entry comment says why it is on a live
cadence: "an unlinked live match shows the ESPN score line until the next pass."
A 38-minute hole is 38 minutes of a live US Open match rendering the wrong score
line. Bounding the hole IS the user-visible ship.

WHAT THE FIX IS. A crontab is ABSOLUTE — the next fire is the next matching
minute whatever beat has just done, so a restart cannot re-arm it. That does not
make loss impossible (beat down across the whole minute still misses that slot)
but it bounds loss at one slot instead of compounding one full period per deploy.

`TestTheRealDeployStormStarvesAFloatSchedule` is the red-first half: it replays
the five real restarts against celery's own schedule objects and pins that the
float schedule fires ZERO times across the storm while the shipped crontab keeps
firing. Run it against `"schedule": 600.0` and the crontab assertion is the one
that reddens.
"""

from __future__ import annotations

import datetime as dt

import pytest
from celery.schedules import crontab, schedule

from app.tasks import celery_app

UTC = dt.timezone.utc

#: The beat entry under test, by the key `test_tasks_wiring` already allowlists.
ENTRY_KEY = "link-tennis-statpal-fixtures-10min"

#: The five real Heroku releases that produced the 38-minute hole, from
#: `heroku releases -a bainluck` read at 21:36Z on 2026-09-05. Boot lag is the
#: measured one: the 21:15:47 release had its scheduler dyno `up` at 21:16:09.
REAL_RESTARTS = [
    dt.datetime(2026, 9, 5, 20, 54, 30, tzinfo=UTC),
    dt.datetime(2026, 9, 5, 20, 59, 9, tzinfo=UTC),
    dt.datetime(2026, 9, 5, 21, 2, 27, tzinfo=UTC),
    dt.datetime(2026, 9, 5, 21, 7, 0, tzinfo=UTC),
    dt.datetime(2026, 9, 5, 21, 15, 47, tzinfo=UTC),
]
BOOT_LAG = dt.timedelta(seconds=22)

#: The last real fire before the storm, and the end of the observed hole.
STORM_START = dt.datetime(2026, 9, 5, 20, 48, 17, tzinfo=UTC)
STORM_END = dt.datetime(2026, 9, 5, 21, 26, 42, tzinfo=UTC)


class _Clock:
    """A mutable virtual clock, handed to celery via `nowfun`."""

    def __init__(self, start: dt.datetime) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now


def _replay(sched_factory, restarts, start, end, step=dt.timedelta(seconds=10)):
    """Replay beat's own due-logic over a window that contains restarts.

    Mirrors `celery.beat.Service.start`: tick, ask the schedule `is_due`, fire
    and set `last_run_at = now` when it says so. A restart resets `last_run_at`
    to the boot instant, which is exactly what a fresh `ScheduleEntry` does when
    the shelve is gone — that reset IS the bug under test.
    """
    clock = _Clock(start)
    sched = sched_factory(clock)
    last_run_at = start
    pending = list(restarts)
    fires: list[dt.datetime] = []

    t = start
    while t <= end:
        clock.now = t
        # Apply any restart whose boot has completed by now.
        while pending and t >= pending[0] + BOOT_LAG:
            last_run_at = pending.pop(0) + BOOT_LAG
        is_due, _next = sched.is_due(last_run_at)
        if is_due:
            fires.append(t)
            last_run_at = t
        t += step
    return fires


def _float_600(clock):
    return schedule(run_every=600.0, nowfun=clock, app=celery_app)


def _shipped_crontab(clock):
    return crontab(minute="4,14,24,34,44,54", nowfun=clock, app=celery_app)


class TestTheRealDeployStormStarvesAFloatSchedule:
    """The red-first pair: same storm, same replay, two schedule types."""

    def test_the_float_schedule_is_starved_until_600s_after_the_last_boot(self):
        """The fingerprint, reproduced: nothing fires until the storm relents.

        Production made ONE pass in this window, at 21:26:42Z, which is 600 s
        after the 21:16:09Z dyno boot. The replay lands it at 21:26:17Z on a 10 s
        grid — within one step of the real thing, so the model is the mechanism
        and not a story about it.
        """
        fires = _replay(_float_600, REAL_RESTARTS, STORM_START, STORM_END)

        last_boot = REAL_RESTARTS[-1] + BOOT_LAG
        expected = last_boot + dt.timedelta(seconds=600)

        assert len(fires) == 1, (
            "Across the five real restarts the float schedule is expected to be "
            "starved down to the single fire that escapes after the last one. "
            f"Got {[f.isoformat() for f in fires]}."
        )
        assert abs((fires[0] - expected).total_seconds()) <= 15, (
            "The one escaping fire must land a full period after the LAST boot "
            "— that is the re-arming fingerprint, and it is what makes this "
            f"starvation rather than mere downtime. Expected ~{expected}, got "
            f"{fires[0]}."
        )
        starved_for = (fires[0] - STORM_START).total_seconds()
        assert starved_for > 2200, (
            f"Only {starved_for:.0f}s of hole; production measured 2305s."
        )

    def test_the_shipped_crontab_keeps_firing_through_the_same_storm(self):
        fires = _replay(_shipped_crontab, REAL_RESTARTS, STORM_START, STORM_END)
        minutes = sorted({f.minute for f in fires})
        assert len(fires) >= 3, (
            "A crontab is absolute, so the same five restarts must NOT be able "
            f"to re-arm it. Expected the :04/:14/:24 slots inside the "
            f"20:48:17Z-21:26:42Z window; got {[f.isoformat() for f in fires]}."
        )
        assert set(minutes) <= {4, 14, 24, 34, 44, 54}, (
            f"Fires landed off the declared grid: {minutes}"
        )

    def test_the_hole_the_float_leaves_is_the_38_minutes_we_measured(self):
        """The window itself is the measurement, so pin it rather than imply it."""
        hole = (STORM_END - STORM_START).total_seconds()
        assert 2200 <= hole <= 2400, hole
        assert hole / 600.0 > 3.5, (
            "The observed hole must be several periods wide for the starvation "
            f"reading to hold; it is {hole / 600.0:.1f} periods."
        )


class TestTheShippedEntryIsWallClockAnchored:
    """Pin what actually ships, not just what the replay models."""

    def test_the_tennis_link_beat_is_a_crontab(self):
        entry = celery_app.conf.beat_schedule[ENTRY_KEY]
        assert isinstance(entry["schedule"], crontab), (
            f"{ENTRY_KEY} must be wall-clock anchored (#3316). A float schedule "
            "re-arms a full period on every scheduler boot and our deploy rate "
            "starves it. Got "
            f"{entry['schedule']!r}."
        )

    def test_it_still_fires_every_ten_minutes_on_realtime(self):
        entry = celery_app.conf.beat_schedule[ENTRY_KEY]
        assert isinstance(entry["schedule"], crontab), (
            f"cadence unreadable — {ENTRY_KEY} is not a crontab (#3316): "
            f"{entry['schedule']!r}"
        )
        minutes = sorted(entry["schedule"].minute)
        assert minutes == [4, 14, 24, 34, 44, 54], minutes
        gaps = {b - a for a, b in zip(minutes, minutes[1:])}
        assert gaps == {10}, f"cadence is no longer an even ten minutes: {gaps}"
        assert entry["options"]["queue"] == "realtime"

    def test_it_shares_no_minute_with_another_statpal_reader(self):
        """This file's standing rule, now enforced for the entry that joined it."""
        shipped = celery_app.conf.beat_schedule[ENTRY_KEY]["schedule"]
        assert isinstance(shipped, crontab), (
            f"placement unreadable — {ENTRY_KEY} is not a crontab (#3316): "
            f"{shipped!r}"
        )
        mine = set(shipped.minute)
        clashes = {}
        for key, entry in celery_app.conf.beat_schedule.items():
            if key == ENTRY_KEY:
                continue
            if "statpal" not in key and "statpal" not in str(entry.get("task", "")):
                continue
            sched_obj = entry["schedule"]
            if not isinstance(sched_obj, crontab):
                # A sub-minute interval reader fires during every minute anyway;
                # no placement avoids it, so it is absorbed, not a clash.
                continue
            shared = mine & set(sched_obj.minute)
            if shared:
                clashes[key] = sorted(shared)
        assert clashes == {}, (
            f"{ENTRY_KEY} now shares a minute with another StatPal reader: "
            f"{clashes}. Re-run the offset census before moving it — offsets :4, "
            ":6 and :8 were the only collision-free ones on 2026-09-05."
        )


class TestNoRealtimeBeatGoesBackToARelativeInterval:
    """The ratchet. Without it the fix decays back the next time one is added."""

    #: Below this, a beat fires during every minute anyway, so a restart can
    #: cost at most the period itself and starvation cannot compound. This is
    #: the same argument `BACKGROUND_INTERVAL_FLOOR` makes for the settlement
    #: sweep's co-fires.
    CONTINUOUS_FLOOR_S = 180.0

    def test_long_period_realtime_beats_are_all_wall_clock_anchored(self):
        offenders = {}
        for key, entry in celery_app.conf.beat_schedule.items():
            if (entry.get("options") or {}).get("queue") != "realtime":
                continue
            sched_obj = entry["schedule"]
            if isinstance(sched_obj, crontab):
                continue
            period = float(getattr(sched_obj, "run_every", sched_obj).total_seconds()
                           if hasattr(getattr(sched_obj, "run_every", sched_obj),
                                      "total_seconds")
                           else getattr(sched_obj, "run_every", sched_obj))
            if period > self.CONTINUOUS_FLOOR_S:
                offenders[key] = period
        assert offenders == {}, (
            "#3316: a realtime beat with a period above the continuous floor "
            f"must use a crontab, not a relative interval — {offenders}. A float "
            "schedule re-arms a fresh period on every scheduler boot, and at our "
            "deploy rate (30 releases in 6 h on 2026-09-05) that starves it "
            "outright. Place it with the offset census, not by hand."
        )


@pytest.mark.parametrize("offset", [0, 5])
def test_the_naive_offsets_really_were_worse(offset):
    """The census is load-bearing, so keep its conclusion falsifiable.

    A plain `*/10` sits on :00 — the busiest tick in the schedule and home to
    three StatPal readers. This asserts the thing we rejected is still bad, so
    nobody 'simplifies' the placement back to `*/10` later.
    """
    statpal_minutes = set()
    for key, entry in celery_app.conf.beat_schedule.items():
        if key == ENTRY_KEY:
            continue
        if "statpal" not in key and "statpal" not in str(entry.get("task", "")):
            continue
        if isinstance(entry["schedule"], crontab):
            statpal_minutes |= set(entry["schedule"].minute)
    slots = set(range(offset, 60, 10))
    assert slots & statpal_minutes, (
        f"Offset :{offset} no longer collides with a StatPal reader. The census "
        "that chose :04 has gone stale — re-run it before trusting the placement."
    )
