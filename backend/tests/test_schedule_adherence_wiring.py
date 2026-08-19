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
        if (key not in self.strings and key not in self.hashes
                and key not in self.lists):
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
        """Real EXPIRE sets the key's TTL. This used to only record the call.

        LAT-P039 named the cost and Alex ruled it into the record: a test double
        that cannot express the bug cannot catch it. `M19` — a mutant that
        removed an `expire` — SURVIVED its first pass here, not because the
        assertion was weak but because the fake had nothing for the mutation to
        change. A no-op double does not make a test lenient, it makes the test
        blind, and blind reads as green.

        `self.calls` is kept as well, so tests that assert on the call itself
        keep working; the TTL is now also applied so `ttl()` can observe it.
        """
        self.calls.append(("expire", key, ttl))
        if key in self.strings or key in self.hashes or key in self.lists:
            self.ttls[key] = ttl

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


class TestDurationSampleCarriesItsOwnWindow:
    """LAT-P040 (#835): the p95's span is measured, not read off ``window_s``.

    The defect this file's own module was written to fix — a count whose age is
    unstated — was still live one field to the right. ``window_s`` ages the
    STARTS counter on a 24h TTL; the duration history is bounded by COUNT, so it
    reaches back fifty times the task's cadence and nothing on the payload said
    so.

    Measured in production 2026-08-11, `poll_odds`: 50 samples (exactly the
    cap), p95 5,821ms, printed beside ``window_s: 68550`` — 19.1 hours. Its own
    counters date the sample: 1,149 starts over 68,673s is one run per 59.8s, so
    fifty of them span ~50 minutes. A 23x mismatch, and the reason an hour-old
    46.2s burst was recorded as a standing property of the beat and staged as
    this queue's top item.

    The clock is INJECTED in every test below. An anchor that samples the wall
    clock is gotcha #44, and a span assertion is precisely the shape that would
    hide it.
    """

    def _push(self, fake, samples):
        """samples: (duration_ms, epoch_s) oldest first."""
        for ms, ts in samples:
            pipe = fake.pipeline()
            redis_state._push_duration(pipe, "t", ms, now_s=ts)
        fake.hashes.setdefault(
            f"{TASK_METRICS_PREFIX}:t", {b"consecutive_failures": b"0"})

    def test_span_is_measured_from_the_samples(self, fake):
        base = 1_786_500_000
        self._push(fake, [(100, base), (200, base + 600), (300, base + 1800)])
        m = redis_state.get_task_metrics("t")
        assert m["recent_durations_ms"] == [300, 200, 100]  # newest first
        assert m["recent_durations_n"] == 3
        assert m["recent_durations_window_s"] == 1800.0
        assert m["recent_durations_saturated"] is False

    def test_a_saturated_sample_says_so(self, fake):
        """At the cap, older runs existed and were dropped.

        This is the load-bearing flag: it lets a reader conclude the p95 cannot
        describe the counter window WITHOUT knowing DURATION_HISTORY_LEN.
        """
        base = 1_786_500_000
        n = redis_state.DURATION_HISTORY_LEN
        self._push(fake, [(i, base + i * 60) for i in range(n + 20)])
        m = redis_state.get_task_metrics("t")
        assert m["recent_durations_n"] == n
        assert m["recent_durations_saturated"] is True
        # Only the surviving samples define the span — the discarded 20 runs
        # must not silently widen it.
        assert m["recent_durations_window_s"] == float((n - 1) * 60)

    def test_the_span_does_not_come_from_the_counter_window(self, fake):
        """The regression that matters: a long counter, a short sample.

        Reproduces the production shape. If `p95_window_s` ever tracks
        `window_s` again, this fails.
        """
        base = 1_786_500_000
        self._push(fake, [(5000, base), (46000, base + 3000)])
        m = redis_state.get_task_metrics("t")
        graded = adherence(
            starts=1149,
            starts_window_s=68673.0,      # 19.1h — the STARTS counter
            interval_s=30.0,
            durations_ms=m["recent_durations_ms"],
            durations_window_s=m["recent_durations_window_s"],
            durations_saturated=m["recent_durations_saturated"],
        )
        assert graded["window_s"] == 68673.0
        assert graded["p95_window_s"] == 3000.0
        assert graded["p95_window_s"] != graded["window_s"]

    def test_an_overrun_reason_names_the_sample_it_came_from(self, fake):
        base = 1_786_500_000
        n = redis_state.DURATION_HISTORY_LEN
        self._push(fake, [(46000, base + i * 60) for i in range(n)])
        m = redis_state.get_task_metrics("t")
        graded = adherence(
            starts=1149, starts_window_s=68673.0, interval_s=30.0,
            durations_ms=m["recent_durations_ms"],
            durations_window_s=m["recent_durations_window_s"],
            durations_saturated=m["recent_durations_saturated"],
        )
        assert graded["verdict"] == "overruns"
        # The number alone was readable as a 19-hour property. The scope is now
        # inseparable from the claim.
        assert "over the last 50 runs" in graded["reason"]
        assert "49min" in graded["reason"]
        assert "saturated" in graded["reason"]

    def test_legacy_unstamped_entries_still_read(self, fake):
        """A bare-int history predates LAT-P040 and must not read as EMPTY.

        Rejecting it would report "this task never ran" for a cap-length after
        every deploy — a false absence, gotcha #53.
        """
        fake.lists[f"{TASK_METRICS_PREFIX}:t:durations"] = [b"300", b"200"]
        fake.hashes.setdefault(
            f"{TASK_METRICS_PREFIX}:t", {b"consecutive_failures": b"0"})
        m = redis_state.get_task_metrics("t")
        assert m["recent_durations_ms"] == [300, 200]
        # Unknown, and said so — never inferred from a counter that ages apart.
        assert m["recent_durations_window_s"] is None
        graded = adherence(
            starts=10, starts_window_s=3600.0, interval_s=30.0,
            durations_ms=m["recent_durations_ms"],
            durations_window_s=m["recent_durations_window_s"],
        )
        assert "span unknown" in graded["reason"] or graded["verdict"] != "overruns"

    def test_a_mixed_history_across_the_deploy_boundary_reads(self, fake):
        """The real shape for one cap-length after release: old + new together."""
        base = 1_786_500_000
        fake.lists[f"{TASK_METRICS_PREFIX}:t:durations"] = [b"900"]
        pipe = fake.pipeline()
        redis_state._push_duration(pipe, "t", 100, now_s=base)
        pipe2 = fake.pipeline()
        redis_state._push_duration(pipe2, "t", 200, now_s=base + 300)
        fake.hashes.setdefault(
            f"{TASK_METRICS_PREFIX}:t", {b"consecutive_failures": b"0"})
        m = redis_state.get_task_metrics("t")
        assert m["recent_durations_ms"] == [200, 100, 900]
        # Two stamped samples are enough to date the sample; the legacy entry
        # contributes its duration but cannot widen the span it never carried.
        assert m["recent_durations_window_s"] == 300.0

    def test_the_durations_key_actually_gets_a_ttl(self, fake):
        """Guards the fake as much as the code — Alex's ruling, LAT-P039 M19.

        `expire()` was a no-op that only appended to `calls`, so a mutant that
        deleted the expire survived. With the double modelling the operation,
        the assertion has something to fail against.
        """
        pipe = fake.pipeline()
        redis_state._push_duration(pipe, "t", 100, now_s=1_786_500_000)
        key = f"{TASK_METRICS_PREFIX}:t:durations"
        assert fake.ttl(key) == redis_state.TASK_METRICS_TTL


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


# ---------------------------------------------------------------------------
# LAT-P071 — the route half of the stamp arm.
#
# The pure grader is tested in test_schedule_adherence.py. What can only be
# tested here is the JOIN: that the route turns the metrics hash's ISO stamps
# into ages against a real clock, reads the counter TTL from the writer's own
# constant, and refuses a stamp that lies in the future.
# ---------------------------------------------------------------------------

class TestStampArmWiring:
    DAY = 86400.0

    @staticmethod
    def _iso(epoch):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    def _sched(self):
        return {"b": {"task": "app.tasks.daily_thing", "schedule": self.DAY}}

    def _run(self, now, **stamps):
        m = _metrics("daily_thing", starts=1, window_s=77000)
        m.update(stamps)
        return build_schedule_adherence(
            self._sched(), [m], {"app.tasks.daily_thing": "daily_thing"},
            now_epoch=now,
        )["all"]["app.tasks.daily_thing"]

    def test_daily_beat_is_graded_instead_of_shrugged_at(self):
        # Before LAT-P071 this returned unmeasurable/window_too_short forever.
        now = 1_787_000_000.0
        g = self._run(now, last_success_at=self._iso(now - 3600))
        assert g["arm"] == "stamp"
        assert g["verdict"] == "on_schedule"
        assert g["rate_arm_blind"] is True

    def test_a_daily_beat_that_skipped_a_whole_day_is_missing(self):
        now = 1_787_000_000.0
        g = self._run(now, last_success_at=self._iso(now - 3 * self.DAY))
        assert g["verdict"] == "missing"

    def test_a_future_stamp_is_refused_not_treated_as_fresh(self):
        # Ahead-drift. A clock-skewed stamp yields a NEGATIVE age, which sails
        # through every `age <= limit` test as the freshest reading possible —
        # certifying a dead beat as healthy. Unknown must beat wrong here.
        now = 1_787_000_000.0
        g = self._run(now, last_success_at=self._iso(now + 7200))
        assert g["verdict"] == "unmeasurable"
        assert g["stamp_age_s"] is None

    def test_a_future_terminal_does_not_hide_a_usable_start(self):
        now = 1_787_000_000.0
        g = self._run(now, last_success_at=self._iso(now + 7200),
                      last_started_at=self._iso(now - 600))
        assert g["verdict"] == "on_schedule"
        assert g["stamp_kind"] == "start"

    def test_failure_and_incomplete_stamps_also_count_as_having_run(self):
        # T5's question is "did it run", not "did it succeed". A daily sentinel
        # that ran and failed is a failing sentinel, not a missing beat, and the
        # two need different remedies.
        now = 1_787_000_000.0
        for field in ("last_failure_at", "last_incomplete_at"):
            g = self._run(now, **{field: self._iso(now - 60)})
            assert g["verdict"] == "on_schedule", field

    def test_the_ttl_ceiling_comes_from_the_writer_not_a_literal(self):
        # If WINDOW_COUNTER_TTL ever moves, the ceiling must move with it or the
        # grader silently mis-classifies which beats are structurally blind.
        from app.tasks.redis_state import WINDOW_COUNTER_TTL
        from app.utils.schedule_adherence import (
            MIN_EXPECTED_FIRES, rate_arm_is_structurally_blind,
        )
        ceiling = WINDOW_COUNTER_TTL / MIN_EXPECTED_FIRES
        assert rate_arm_is_structurally_blind(ceiling + 1, WINDOW_COUNTER_TTL)
        assert not rate_arm_is_structurally_blind(ceiling - 1, WINDOW_COUNTER_TTL)

    def test_arm_counts_separate_the_two_kinds_of_pass(self):
        # A stamp-arm pass says only "something happened recently"; a rate-arm
        # pass says "it fired N times in a measured window". One tally for both
        # would launder the weaker evidence into the stronger one's confidence.
        now = 1_787_000_000.0
        sched = {
            "d": {"task": "app.tasks.daily_thing", "schedule": self.DAY},
            "m": {"task": "app.tasks.minute_thing", "schedule": 60.0},
        }
        daily = _metrics("daily_thing", starts=1, window_s=77000)
        daily["last_success_at"] = self._iso(now - 3600)
        out = build_schedule_adherence(
            sched, [daily, _metrics("minute_thing", starts=59, window_s=3600)],
            {"app.tasks.daily_thing": "daily_thing",
             "app.tasks.minute_thing": "minute_thing"},
            now_epoch=now,
        )
        assert out["arm_counts"]["stamp"] == {"on_schedule": 1}
        assert out["arm_counts"]["rate"] == {"on_schedule": 1}
        assert out["arm_counts"]["rate_arm_blind_total"] == 1

    def test_the_blind_census_is_a_schedule_property_not_a_health_one(self):
        # It must not fall to zero just because every blind beat is healthy —
        # that is the number that says how much of the schedule the rate arm
        # could never grade, and it should only move when the schedule does.
        now = 1_787_000_000.0
        daily = _metrics("daily_thing", starts=1, window_s=77000)
        daily["last_success_at"] = self._iso(now - 60)
        out = build_schedule_adherence(
            self._sched(), [daily], {"app.tasks.daily_thing": "daily_thing"},
            now_epoch=now,
        )
        assert out["verdict_counts"] == {"on_schedule": 1}
        assert out["arm_counts"]["rate_arm_blind_total"] == 1

    def test_the_route_guard_itself_rejects_a_future_stamp(self):
        # Found by mutation: `test_a_future_stamp_is_refused...` above passes
        # even with this guard deleted, because the pure grader ALSO drops
        # negative ages. Two independent guards, one test — removing either one
        # alone was invisible. This pins the route half on its own.
        from app.routes.admin_celery import _stamp_ages_s
        now = 1_787_000_000.0
        terminal, start = _stamp_ages_s(
            {"last_success_at": self._iso(now + 7200),
             "last_started_at": self._iso(now - 300)}, now,
        )
        assert terminal is None
        assert start == pytest.approx(300.0)
