"""LAT-P022 (#1609): the storage and the join behind the adherence verdict.

``test_schedule_adherence.py`` grades numbers. This file checks that the
numbers exist and reach the grader: the counter window is stamped, the duration
history is bounded and written on every terminal, the celery-name-to-label map
is recorded from real runs, and the route joins the three without inventing a
task that is not scheduled or dropping one that is.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.admin_celery import build_schedule_adherence
from app.tasks import redis_state
from app.tasks.redis_state import TASK_LABEL_MAP_KEY, TASK_METRICS_PREFIX


class _Redis:
    """Enough Redis for the metrics writer/reader, including lists."""

    def __init__(self):
        self.strings = {}
        self.hashes = {}
        self.lists = {}
        self.calls = []

    # --- read -------------------------------------------------------------
    def get(self, key):
        return self.strings.get(key)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field.encode())

    def lrange(self, key, start, end):
        return list(self.lists.get(key, []))[start:end + 1]

    def keys(self, _pattern):
        out = set(self.hashes) | {
            k.rsplit(":", 1)[0] for k in self.strings if k.endswith(":successes")
        }
        return [k.encode() for k in out]

    # --- write ------------------------------------------------------------
    def pipeline(self):
        return self

    def execute(self):
        return []

    def hset(self, key, field=None, value=None, mapping=None):
        target = self.hashes.setdefault(key, {})
        if mapping:
            for f, v in mapping.items():
                target[f.encode()] = str(v).encode()
        if field is not None:
            target[field.encode()] = str(value).encode()

    def expire(self, key, ttl):
        self.calls.append(("expire", key, ttl))

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.strings:
            return None
        self.strings[key] = str(value).encode()
        return True

    def incr(self, key):
        self.strings[key] = str(int(self.strings.get(key, b"0")) + 1).encode()

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, str(value).encode())

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]


@pytest.fixture
def fake(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    return r


class TestCounterWindowIsStamped:
    def test_success_stamps_the_window_once(self, fake):
        for _ in range(5):
            redis_state.record_task_success("t", 100.0, {})
        key = f"{TASK_METRICS_PREFIX}:t:successes"
        assert fake.strings[key] == b"5"
        assert f"{key}:since" in fake.strings

    def test_the_stamp_does_not_move_on_later_increments(self, fake):
        redis_state.record_task_success("t", 100.0, {})
        first = fake.strings[f"{TASK_METRICS_PREFIX}:t:successes:since"]
        for _ in range(4):
            redis_state.record_task_success("t", 100.0, {})
        # If it slid, the window would always read ~0s old and the rate would be
        # divided by nothing — the same class of bug as the sliding EXPIRE that
        # made these counters lifetime totals in the first place.
        assert fake.strings[f"{TASK_METRICS_PREFIX}:t:successes:since"] == first

    def test_starts_counter_is_stamped_too(self, fake):
        redis_state.record_task_started("t")
        assert f"{TASK_METRICS_PREFIX}:t:starts:since" in fake.strings

    def test_window_age_is_reported_in_seconds(self, fake):
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        fake.strings[f"{TASK_METRICS_PREFIX}:t:starts:since"] = past.encode()
        fake.strings[f"{TASK_METRICS_PREFIX}:t:starts"] = b"7"
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
        m = redis_state.get_task_metrics("t")
        assert m["starts_window_s"] == pytest.approx(7200, abs=60)

    def test_missing_stamp_reads_none_not_zero(self, fake):
        # A zero age reads as an infinitely fast rate, which would make every
        # counter written before this shipped look like thousands of fires/sec.
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
        assert redis_state.get_task_metrics("t")["starts_window_s"] is None


class TestDurationHistory:
    def test_history_is_written_newest_first(self, fake):
        for ms in (100, 200, 300):
            redis_state.record_task_success("t", ms, {})
        fake.hashes.setdefault(f"{TASK_METRICS_PREFIX}:t", {})
        assert redis_state.get_task_metrics("t")["recent_durations_ms"] == [
            300, 200, 100,
        ]

    def test_history_is_bounded(self, fake):
        for i in range(redis_state.DURATION_HISTORY_LEN + 25):
            redis_state.record_task_success("t", i, {})
        stored = fake.lists[f"{TASK_METRICS_PREFIX}:t:durations"]
        # Bounded on every write, not by TTL: on an allkeys-lru instance an
        # unbounded key does not merely cost memory, it evicts other keys.
        assert len(stored) == redis_state.DURATION_HISTORY_LEN

    def test_failures_and_incompletes_also_record_a_duration(self, fake):
        redis_state.record_task_failure("t", 900.0, "boom")
        redis_state.record_task_incomplete("t", 800.0, "partial", "stopped")
        fake.hashes.setdefault(f"{TASK_METRICS_PREFIX}:t", {})
        # A lapping task's expensive runs are frequently the ones that end
        # badly; a happy-path-only history under-reports the very tail this
        # exists to measure.
        assert redis_state.get_task_metrics("t")["recent_durations_ms"] == [800, 900]


class TestLabelMap:
    def test_records_the_running_celery_task_name(self, fake, monkeypatch):
        import celery

        class _Req:
            task = "app.tasks.precompute_discover_candidate_base"

        monkeypatch.setattr(celery, "current_task",
                            type("T", (), {"request": _Req()})())
        redis_state.record_task_label("precompute_discover_candidate_base")
        assert redis_state.get_task_label_map() == {
            "app.tasks.precompute_discover_candidate_base":
                "precompute_discover_candidate_base",
        }

    def test_outside_a_worker_nothing_is_recorded(self, fake, monkeypatch):
        # An ad-hoc admin invocation has no request and says nothing about a
        # schedule; recording it would map a label to whatever ran last.
        import celery

        monkeypatch.setattr(celery, "current_task",
                            type("T", (), {"request": None})())
        redis_state.record_task_label("whatever")
        assert redis_state.get_task_label_map() == {}

    def test_label_map_is_not_read_back_as_a_task(self, fake):
        # It lives under the metrics prefix and is three parts deep like a task
        # key, and it is a NON-EMPTY hash — so without the exclusion it would
        # not even return `no_data`; it would emit a phantom task named
        # "label_map" onto the health surface.
        fake.hashes[TASK_LABEL_MAP_KEY] = {b"app.tasks.foo": b"foo"}
        fake.hashes[f"{TASK_METRICS_PREFIX}:foo"] = {b"consecutive_failures": b"0"}
        names = [m.get("task") for m in redis_state.get_all_task_metrics()]
        assert "label_map" not in names
        assert "foo" in names


def _metrics(label, starts, window_s, durations=(), terminals=None):
    return {
        "task": label,
        "starts_24h": starts,
        "starts_window_s": window_s,
        "successes_24h": starts if terminals is None else terminals,
        "failures_24h": 0,
        "incompletes_24h": 0,
        "recent_durations_ms": list(durations),
    }


class TestRouteJoin:
    def test_grades_a_scheduled_task_that_has_metrics(self):
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.foo", "schedule": 60.0}},
            [_metrics("foo", starts=10, window_s=3600)],
            {"app.tasks.foo": "foo"},
        )
        assert out["graded"] == 1
        assert out["lapping"][0]["task"] == "app.tasks.foo"
        assert out["lapping"][0]["verdict"] == "behind"

    def test_scheduled_task_with_no_label_is_reported_unmapped_not_dropped(self):
        # 32 beat entries had no metric label at all when this was measured.
        # Dropping them would make "we grade every scheduled task" true only of
        # the ones that were already visible.
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.invisible", "schedule": 60.0}}, [], {},
        )
        assert out["graded"] == 0
        assert out["unmapped"] == [{
            "task": "app.tasks.invisible", "interval_s": 60.0,
            "reason": "no_metric_label_recorded",
        }]

    def test_a_label_with_no_metrics_is_distinguished_from_no_label(self):
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.foo", "schedule": 60.0}}, [],
            {"app.tasks.foo": "foo"},
        )
        assert out["unmapped"][0]["reason"] == "label_recorded_but_no_metrics"

    def test_a_recorded_task_that_is_not_scheduled_is_not_graded(self):
        # Metrics exist for ad-hoc and admin-triggered tasks too. Grading one
        # against a cadence it does not have would invent a lapping task.
        out = build_schedule_adherence(
            {}, [_metrics("manual_thing", starts=1, window_s=3600)], {},
        )
        assert out["scheduled_tasks"] == 0 and out["lapping"] == []

    def test_on_schedule_tasks_stay_out_of_the_work_list(self):
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.foo", "schedule": 60.0}},
            [_metrics("foo", starts=59, window_s=3600)],
            {"app.tasks.foo": "foo"},
        )
        assert out["lapping"] == []
        assert out["verdict_counts"] == {"on_schedule": 1}

    def test_multi_entry_task_is_graded_against_its_combined_cadence(self):
        # Four hourly entries, one task: 4 fires/hour expected, not 1. Graded
        # against a single entry's interval, 4 fires in an hour would read as
        # 4x over-firing rather than exactly on schedule.
        sched = {
            f"e{i}": {"task": "app.tasks.sync_statpal_schedules",
                      "schedule": 3600.0}
            for i in range(4)
        }
        out = build_schedule_adherence(
            sched,
            [_metrics("sync_statpal_schedules", starts=8, window_s=7200)],
            {"app.tasks.sync_statpal_schedules": "sync_statpal_schedules"},
        )
        graded = out["all"]["app.tasks.sync_statpal_schedules"]
        assert graded["interval_s"] == 900.0
        assert graded["verdict"] == "on_schedule"
