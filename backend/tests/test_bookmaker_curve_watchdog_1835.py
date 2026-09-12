"""#1835 (CAL-P1122): the accuracy page stops freezing when one input expires.

`bainluck:bookmaker_calibration` holds the whole `odds_api_bookmaker` source
(~96K outcomes). The calibration producer refuses to publish while it is absent
— correctly, D21/#1978 — so an expired key does not degrade the accuracy page,
it FREEZES it, until a person notices and re-runs the writer by hand.

Measured 2026-09-12: four consecutive hourly builds refused 19 ms into their
diagnostics phase and the page served a 4.6-hour-old curve. The writer itself
was healthy the whole time — run from a one-off dyno it returned
`terminal: complete` in 196.5 s. It was being killed by releases, four times in
a row, six hours apart.

Two things ship against that, and these tests pin both:

* the writer's cadence goes 6h -> 2h, so the 24h TTL gets twelve chances
  instead of four (`TestTheCadenceIsTheRepair`);
* the watchdog alarms when the key is absent for longer than one cadence —
  the case the cadence cannot fix, a writer that arrives and does not land.

The tests that matter most are the ones asserting the watchdog stays QUIET: an
alarm that fires on every ordinary gap between two writer fires is an alarm
everyone learns to ignore, and then the real one is invisible too.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import watchdog

NOW = datetime(2026, 9, 12, 6, 0, 0, tzinfo=timezone.utc)


class _FakeRedis:
    """Sync Redis stand-in; `get_raises` drives the unreadable-Redis path."""

    def __init__(self, initial=None, get_raises=False):
        self.store = dict(initial or {})
        self.get_raises = get_raises
        self.deleted = []

    def get(self, key):
        if self.get_raises:
            raise RuntimeError("redis down")
        v = self.store.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def alerts(monkeypatch):
    """Capture alarms instead of emitting them; the list is asserted on."""
    emitted = []
    monkeypatch.setattr(
        watchdog,
        "_alert",
        lambda alert_class, provider, msg: emitted.append((alert_class, provider, msg))
        or True,
    )
    return emitted


def _absent_since(seconds_ago):
    return {
        watchdog._BOOKMAKER_ABSENT_SINCE_KEY: (
            NOW - timedelta(seconds=seconds_ago)
        ).isoformat()
    }


class TestTheCadenceIsTheRepair:
    """The watchdog only reports. What actually stops the page freezing is the
    writer getting enough attempts inside the key's 24h TTL."""

    def test_the_writer_fires_at_least_twelve_times_a_day(self):
        """Four attempts against a 24h TTL is what went dark three times in four
        days (8/29, 9/9, 9/12). Twelve needs twelve consecutive kills."""
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule["precompute-bookmaker-calibration"]
        fires = len(set(schedule["schedule"].hour)) * len(
            set(schedule["schedule"].minute)
        )
        assert fires >= 12, f"only {fires} writer fires a day against a 24h TTL"

    def test_no_gap_between_fires_reaches_a_quarter_of_the_keys_ttl(self):
        """The bound that matters is the LARGEST gap, not the average: the key
        dies in the longest one. The TTL is 86400 s, and the comparison is
        STRICT on purpose — 21600 s is exactly the 6h cadence that went dark on
        8/29, 9/9 and 9/12, so a bound that admits it admits the outage."""
        assert watchdog._writer_cadence_seconds() < 86400 // 4

    def test_the_cadence_is_read_from_the_beat_and_not_retyped(self):
        """Derived, so it cannot keep an old value the day the beat moves."""
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule["precompute-bookmaker-calibration"][
            "schedule"
        ]
        slots = sorted(
            h * 60 + m for h in schedule.hour for m in schedule.minute
        )
        gaps = [b - a for a, b in zip(slots, slots[1:])]
        gaps.append(slots[0] + 24 * 60 - slots[-1])
        assert watchdog._writer_cadence_seconds() == max(gaps) * 60

    def test_the_wrap_around_gap_is_counted(self):
        """A schedule clustered early in the day has its longest gap overnight,
        and a non-circular max would report a comfortable number for a beat that
        is silent for 20 hours."""
        from celery.schedules import crontab

        clustered = {"w": {"task": watchdog.BOOKMAKER_WRITER_TASK,
                           "schedule": crontab(minute=0, hour="0,1,2,3")}}

        class _Conf:
            beat_schedule = clustered

        class _App:
            conf = _Conf()

        import sys
        import types

        stub = types.ModuleType("app.tasks")
        stub.celery_app = _App()
        real = sys.modules["app.tasks"]
        sys.modules["app.tasks"] = stub
        try:
            assert watchdog._writer_cadence_seconds() == 21 * 3600
        finally:
            sys.modules["app.tasks"] = real


class TestTheWatchdogStaysQuietWhenItShould:
    def test_a_present_key_says_nothing(self, alerts):
        rc = _FakeRedis({watchdog.BOOKMAKER_CURVE_KEY: "[]"})

        result = watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert result == {"key_present": True, "alerted": False}
        assert alerts == []

    def test_a_present_key_clears_the_absence_clock(self, alerts):
        """Otherwise a stale marker makes the NEXT absence look hours old and
        pages immediately."""
        rc = _FakeRedis(
            {watchdog.BOOKMAKER_CURVE_KEY: "[]", **_absent_since(99999)}
        )

        watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert watchdog._BOOKMAKER_ABSENT_SINCE_KEY in rc.deleted
        assert watchdog._BOOKMAKER_ABSENT_SINCE_KEY not in rc.store

    def test_a_first_sighting_of_an_absence_records_and_does_not_alarm(self, alerts):
        rc = _FakeRedis()

        result = watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert result == {"key_present": False, "alerted": False, "absent_seconds": 0}
        assert alerts == []
        assert rc.store[watchdog._BOOKMAKER_ABSENT_SINCE_KEY] == NOW.isoformat()

    def test_an_absence_shorter_than_one_cadence_does_not_alarm(self, alerts):
        """The key is rewritten by a beat, not continuously. The gap between an
        expiry and the next fire is housekeeping, and paging on it is how an
        alarm gets trained away."""
        inside = watchdog._writer_cadence_seconds() - 60
        rc = _FakeRedis(_absent_since(inside))

        result = watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert result["alerted"] is False
        assert alerts == []

    def test_an_unreadable_redis_starts_no_absence_clock(self, alerts):
        """Cannot tell present from absent ⇒ claim neither. Recording an absence
        here would invent one out of a Redis blip and alarm a cadence later."""
        rc = _FakeRedis(get_raises=True)

        result = watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert result["key_present"] is None
        assert result["reason"] == "redis_unreadable"
        assert watchdog._BOOKMAKER_ABSENT_SINCE_KEY not in rc.store
        assert alerts == []

    def test_an_unparseable_marker_restarts_the_clock_rather_than_alarming(
        self, alerts
    ):
        rc = _FakeRedis({watchdog._BOOKMAKER_ABSENT_SINCE_KEY: "not-a-timestamp"})

        result = watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert result["alerted"] is False
        assert rc.store[watchdog._BOOKMAKER_ABSENT_SINCE_KEY] == NOW.isoformat()


class TestTheWatchdogAlarmsWhenItShould:
    def test_an_absence_past_one_cadence_plus_grace_alarms(self, alerts):
        """A fire has come and gone without landing — the cadence cannot fix
        that, so it is a person's problem."""
        past = (
            watchdog._writer_cadence_seconds()
            + watchdog.BOOKMAKER_ABSENCE_GRACE_SECONDS
            + 60
        )
        rc = _FakeRedis(_absent_since(past))

        result = watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        assert result["alerted"] is True
        assert [a[0] for a in alerts] == ["bookmaker_curve_absent"]

    def test_the_alarm_names_the_reader_symptom_and_where_to_look(self, alerts):
        """#1835's first outage lasted 23 hours because the alarm named a Redis
        key and not a frozen page."""
        past = watchdog._writer_cadence_seconds() * 3
        rc = _FakeRedis(_absent_since(past))

        watchdog._run_bookmaker_curve_watchdog(rc=rc, now=NOW)

        msg = alerts[0][2]
        assert "ACCURACY PAGE IS FROZEN" in msg.upper()
        assert "task-metrics/bookmaker_calibration" in msg
        assert "#1835" in msg

    def test_the_grace_is_not_wide_enough_to_swallow_a_whole_cadence(self):
        """Grace exists for clock skew and a slow run, not for a second missed
        fire — otherwise the alarm is a cadence late by construction."""
        assert (
            watchdog.BOOKMAKER_ABSENCE_GRACE_SECONDS
            < watchdog._writer_cadence_seconds()
        )


class TestWiredIntoTheBeat:
    @pytest.mark.asyncio
    async def test_the_summary_carries_the_bookmaker_curve_result(self, monkeypatch):
        async def _no_creation():
            return {}

        monkeypatch.setattr(watchdog, "_run_creation_freshness_watchdog", _no_creation)
        monkeypatch.setattr(
            watchdog, "_run_phase_heartbeat_watchdog", lambda: {"stuck": []}
        )
        monkeypatch.setattr(
            watchdog,
            "_run_bookmaker_curve_watchdog",
            lambda: {"key_present": True, "alerted": False},
        )
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: _FakeRedis())

        summary = await watchdog._run_freshness_watchdog()

        assert summary["bookmaker_curve"] == {"key_present": True, "alerted": False}

    @pytest.mark.asyncio
    async def test_a_raising_check_does_not_take_the_older_checks_down(
        self, monkeypatch
    ):
        """This check is newer than the two beside it and must never be why they
        stop running."""

        async def _creation():
            return {"sentinel": "creation ran"}

        def _boom():
            raise RuntimeError("unexpected")

        monkeypatch.setattr(watchdog, "_run_creation_freshness_watchdog", _creation)
        monkeypatch.setattr(
            watchdog, "_run_phase_heartbeat_watchdog", lambda: {"stuck": []}
        )
        monkeypatch.setattr(watchdog, "_run_bookmaker_curve_watchdog", _boom)
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: _FakeRedis())

        summary = await watchdog._run_freshness_watchdog()

        assert summary["creation"] == {"sentinel": "creation ran"}
        assert summary["bookmaker_curve"]["reason"] == "raised"
