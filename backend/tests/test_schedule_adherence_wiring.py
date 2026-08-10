"""LAT-P022 (#1609): the storage and the join behind the adherence verdict.

``test_schedule_adherence.py`` grades numbers. This file checks that the
numbers exist and reach the grader: the counter window is measurable, the
duration history is bounded and written on every terminal, the celery-name-to-
label map is recorded from real runs, and the route joins the three without
inventing a task that is not scheduled or dropping one that is.

LAT-P024 (#1609) replaced the window's storage. It was a ``:since`` sibling key
written beside the counter; it is now the counter's own TTL. See
``TestCounterWindowIsItsOwnTTL`` for the production measurement that forced it.
"""

import pytest

from app.routes.admin_celery import build_schedule_adherence
from app.tasks import redis_state
from app.utils.schedule_adherence import adherence
from app.tasks.redis_state import TASK_LABEL_MAP_KEY, TASK_METRICS_PREFIX


class _Redis:
    """Enough Redis for the metrics writer/reader, including lists."""

    def __init__(self):
        self.strings = {}
        self.hashes = {}
        self.lists = {}
        self.calls = []
        #: key -> remaining TTL in seconds, modelling real Redis semantics:
        #: a key absent from here but present in the store has NO expiry, which
        #: `ttl()` reports as -1 and which LAT-P024 must read as unmeasurable
        #: rather than as a fresh window.
        self.ttls = {}

    # --- read -------------------------------------------------------------
    def get(self, key):
        return self.strings.get(key)

    def ttl(self, key):
        """Redis TTL contract: -2 no such key, -1 key exists with no expiry."""
        if key not in self.strings and key not in self.hashes:
            return -2
        return self.ttls.get(key, -1)

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
        if ex is not None:
            self.ttls[key] = ex
        return True

    def incr(self, key):
        # Real INCR creates a missing key with NO expiry and never refreshes an
        # existing one. Both halves matter here: the first is how a counter
        # becomes an unbounded lifetime total, the second is what makes the TTL
        # a trustworthy window start.
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


class TestCounterWindowIsItsOwnTTL:
    """LAT-P024 (#1609): the window is the counter's TTL, not a sibling key.

    The previous contract stamped a ``:since`` key alongside the counter under
    the same ``NX`` and TTL. That is correct only for a pair born together, and
    ``NX`` is exactly what prevents the pair from ever being corrected once
    anything separates their birthdays. Production, 2026-08-10: an hourly
    ``crontab(minute=25)`` beat reported 16 fires in a 6.47h window, which
    requires 2.47 schedulers to be true.
    """

    def _counter(self, task="t", kind="starts"):
        return f"{TASK_METRICS_PREFIX}:{task}:{kind}"

    def test_counter_is_created_with_the_window_ttl(self, fake):
        for _ in range(5):
            redis_state.record_task_success("t", 100.0, {})
        key = self._counter(kind="successes")
        assert fake.strings[key] == b"5"
        assert fake.ttls[key] == redis_state.WINDOW_COUNTER_TTL

    def test_no_sibling_since_key_is_written(self, fake):
        # The whole defect was a second key that could disagree with the first.
        # If one comes back, so does the drift.
        redis_state.record_task_started("t")
        redis_state.record_task_success("t", 100.0, {})
        assert [k for k in fake.strings if k.endswith(":since")] == []

    def test_later_increments_do_not_slide_the_window(self, fake):
        redis_state.record_task_success("t", 100.0, {})
        key = self._counter(kind="successes")
        fake.ttls[key] = 40000  # 13.9h into the window
        for _ in range(4):
            redis_state.record_task_success("t", 100.0, {})
        # A refreshed expiry would make the window read ~0s old forever and the
        # rate would be divided by nothing — gotcha #118's original shape.
        assert fake.ttls[key] == 40000

    def test_window_age_is_reported_in_seconds(self, fake):
        key = self._counter()
        fake.strings[key] = b"7"
        fake.ttls[key] = redis_state.WINDOW_COUNTER_TTL - 7200
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
        assert redis_state.get_task_metrics("t")["starts_window_s"] == 7200

    def test_absent_counter_reads_none_not_zero(self, fake):
        # A zero age reads as an infinitely fast rate.
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
        assert redis_state.get_task_metrics("t")["starts_window_s"] is None

    def test_counter_with_no_expiry_is_unmeasurable_not_fresh(self, fake):
        # A bare INCR from outside `_bump_window_counter` creates a key with no
        # TTL. That is an unbounded lifetime total, and reporting it as a fresh
        # window is the exact reading gotcha #118 was banked to stop.
        key = self._counter()
        fake.strings[key] = b"4000"
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
        assert fake.ttl(key) == -1
        assert redis_state.get_task_metrics("t")["starts_window_s"] is None

    def test_ttl_longer_than_the_window_is_refused(self, fake):
        # Written under a different TTL regime. Clamping to 0 would report a
        # brand-new window for an old key — the infinitely-fast-rate reading.
        key = self._counter()
        fake.strings[key] = b"9"
        fake.ttls[key] = redis_state.WINDOW_COUNTER_TTL + 1
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
        assert redis_state.get_task_metrics("t")["starts_window_s"] is None

    def test_the_production_defect_cannot_recur(self, fake):
        """The regression, stated as the arithmetic that exposed it.

        A counter born at one release and a window born at a later one. Under
        the old sibling-key scheme the age came from the LATER birth, so an
        hourly beat's 16 fires landed in a 6.47h window. Reading the age off the
        counter's own TTL makes that unrepresentable: the count and the window
        are two views of one key.
        """
        key = self._counter()
        # v3740 21:56 PT -> read 13:53 PT the next day = 16.0h of accumulation.
        age_s = 16 * 3600
        fake.strings[key] = b"16"
        fake.ttls[key] = redis_state.WINDOW_COUNTER_TTL - age_s
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}

        window_s = redis_state.get_task_metrics("t")["starts_window_s"]
        assert window_s == age_s

        schedulers_implied = 16 / (window_s / 3600.0)
        assert schedulers_implied == pytest.approx(1.0, abs=0.01), (
            "an hourly crontab beat cannot fire more than once per hour per "
            "scheduler; a non-integer implied count means the window is wrong"
        )

    def test_a_rolled_counter_is_unmeasurable_not_behind(self, fake):
        """The mirror-image error, which is the one that manufactures alarms.

        The sibling scheme failed in BOTH directions and only one of them was
        visible. A stamp younger than its counter inflates the rate, and the
        grader has no "ahead" band, so it passed silently as ``on_schedule``.
        A stamp OLDER than its counter — which is what a counter roll produces,
        because the surviving stamp makes the next ``SET NX`` decline — divides
        a near-zero count by a long window and grades a perfectly healthy beat
        ``behind``.

        That was not hypothetical on 2026-08-10: the counters were due to roll
        at 21:56 PT while their stamps lived until 07:15 PT the next morning,
        leaving a 9h19m window in which every graded task would have reported
        ``ratio 0.07`` against ``BEHIND_RATIO 0.6``. A detector that cries wolf
        across its whole population in one night is a detector that gets muted.

        With the window read off the counter's own TTL, a rolled counter has a
        SHORT window by construction, so the grader refuses to grade it — the
        honest answer ``MIN_EXPECTED_FIRES`` exists to give.
        """
        key = self._counter()
        # One fire, two minutes after the roll.
        fake.strings[key] = b"1"
        fake.ttls[key] = redis_state.WINDOW_COUNTER_TTL - 120
        fake.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}

        window_s = redis_state.get_task_metrics("t")["starts_window_s"]
        assert window_s == 120

        graded = adherence(starts=1, starts_window_s=window_s, interval_s=3600)
        assert graded["verdict"] == "unmeasurable"
        assert "window_too_short" in graded["reason"]

        # And the alarm the old scheme would have raised on the same fire.
        stale_stamp_window_s = 14.69 * 3600
        false_alarm = adherence(
            starts=1, starts_window_s=stale_stamp_window_s, interval_s=3600
        )
        assert false_alarm["verdict"] == "behind"


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
