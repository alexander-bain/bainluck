"""#10983 — every heavy beat message expires at max(its period, 15 min).

The heavy queue held ~19 h of FIFO backlog (977 → 1,019 messages, 2026-10-13)
because demand slightly exceeds two slots and no heavy beat message ever
expired, so `refresh_stale_futures_prices` served day-old dispatches and the
World Series board (#1845) sat stale through a playoff game.
"""

from celery.schedules import crontab

from app.tasks import (
    HEAVY_BEAT_EXPIRES_FLOOR_S,
    _crontab_period_seconds,
    apply_heavy_beat_expires,
    celery_app,
)


def _heavy_entries():
    return {
        name: entry
        for name, entry in celery_app.conf.beat_schedule.items()
        if (entry.get("options") or {}).get("queue") == "heavy"
    }


class TestEveryHeavyBeatExpires:
    def test_there_are_heavy_entries(self):
        # Non-vacuity: the loop below must have something to check.
        assert len(_heavy_entries()) >= 30

    def test_every_heavy_entry_carries_expires(self):
        missing = [n for n, e in _heavy_entries().items() if "expires" not in e["options"]]
        assert missing == [], (
            "heavy beat entries with no expires — a new schedule shape "
            f"_crontab_period_seconds cannot read? {missing}"
        )

    def test_expires_is_period_floored_at_fifteen_minutes(self):
        for name, entry in _heavy_entries().items():
            period = _crontab_period_seconds(entry["schedule"])
            assert entry["options"]["expires"] == max(period, HEAVY_BEAT_EXPIRES_FLOOR_S), name

    def test_the_named_specimens(self):
        schedule = celery_app.conf.beat_schedule
        # #1845's task: hourly, so a dispatch older than an hour is dropped.
        assert schedule["refresh-stale-futures-prices-hourly"]["options"]["expires"] == 3600
        # The 5-minute tasks are floored, not dropped the moment the queue is 5 min deep.
        assert schedule["suspend-venue-ended-events"]["options"]["expires"] == 900
        assert schedule["refresh-polymarket-fixture-starts"]["options"]["expires"] == 900
        # Uneven 15-minute minutes resolve to their widest gap.
        assert schedule["match-prediction-markets"]["options"]["expires"] == 900
        assert schedule["calibration-sentinel-weekly"]["options"]["expires"] == 7 * 86400


class TestApplyHeavyBeatExpires:
    def test_an_explicit_expires_is_kept(self):
        schedule = {
            "x": {"task": "t", "schedule": crontab(minute=0), "options": {"queue": "heavy", "expires": 42}}
        }
        apply_heavy_beat_expires(schedule)
        assert schedule["x"]["options"]["expires"] == 42

    def test_non_heavy_entries_are_untouched(self):
        schedule = {
            "bg": {"task": "t", "schedule": crontab(minute=0), "options": {"queue": "background"}},
            "bare": {"task": "t", "schedule": crontab(minute=0)},
        }
        apply_heavy_beat_expires(schedule)
        assert schedule["bg"]["options"] == {"queue": "background"}
        assert "options" not in schedule["bare"]

    def test_heavy_entry_gets_period(self):
        schedule = {
            "h": {"task": "t", "schedule": crontab(minute=0, hour="*/2"), "options": {"queue": "heavy"}}
        }
        apply_heavy_beat_expires(schedule)
        assert schedule["h"]["options"]["expires"] == 7200


class TestCrontabPeriod:
    def test_every_five_minutes(self):
        assert _crontab_period_seconds(crontab(minute="*/5")) == 300

    def test_uneven_minutes_take_the_widest_gap(self):
        assert _crontab_period_seconds(crontab(minute="0,10")) == 3000

    def test_hours_wrap_across_midnight(self):
        assert _crontab_period_seconds(crontab(minute=0, hour="1,7,13,19")) == 6 * 3600
        assert _crontab_period_seconds(crontab(minute=7, hour="1-23/2")) == 2 * 3600

    def test_weekly(self):
        assert _crontab_period_seconds(crontab(minute=20, hour=6, day_of_week=1)) == 7 * 86400

    def test_unreadable_shapes_return_none(self):
        assert _crontab_period_seconds(crontab(minute=0, hour=0, day_of_month=1)) is None
        assert _crontab_period_seconds(300) is None
