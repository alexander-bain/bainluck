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
# The whole module, bound once. Importing it is also what connects the
# `before_task_publish` / `task_prerun` handlers the end-to-end tests drive.
from app import tasks as tasks_mod
from app.tasks import _published_retries, _published_task_name
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

    def test_the_per_sample_stamps_are_exposed_and_positionally_aligned(self, fake):
        """LAT-P079 (#2071): the stamps were parsed and then discarded.

        Every "did this sample happen after X?" question was therefore
        answered by ESTIMATE from a 24h counter — ruling 110's falsifier was
        estimating a three-week horizon for a fact sitting in the data. The
        alignment is the load-bearing half: `recent_durations_at[i]` must
        describe `recent_durations_ms[i]`, or a caller slicing "the post-move
        samples" gets a confident answer about the wrong runs.
        """
        base = 1_786_500_000
        self._push(fake, [(100, base), (200, base + 600), (300, base + 1800)])
        m = redis_state.get_task_metrics("t")
        assert m["recent_durations_ms"] == [300, 200, 100]
        assert m["recent_durations_at"] == [base + 1800, base + 600, base]
        assert len(m["recent_durations_at"]) == len(m["recent_durations_ms"])

    def test_a_legacy_unstamped_entry_holds_its_position_as_None(self, fake):
        """The bare pre-LAT-P040 form has no stamp. It must occupy its slot as
        `None` rather than be skipped — skipping shifts every later stamp onto
        the wrong duration, which is worse than having no stamps at all."""
        base = 1_786_500_000
        self._push(fake, [(100, base), (200, base + 600)])
        # a legacy bare entry, pushed at the head the way the old writer did
        fake.lists[f"{TASK_METRICS_PREFIX}:t:durations"].insert(0, b"555")
        m = redis_state.get_task_metrics("t")
        assert m["recent_durations_ms"] == [555, 200, 100]
        assert m["recent_durations_at"] == [None, base + 600, base]
        # and the window still comes only from the real stamps
        assert m["recent_durations_window_s"] == 600.0

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
        # LAT-P238 added the emit pair to this entry, defaulted on every row so
        # its absence stays readable. Still asserted by EQUALITY, deliberately:
        # a subset assertion here would let a future field be dropped onto an
        # unmapped entry unnoticed, and this row is the surface's only report of
        # a beat it cannot grade.
        assert out["unmapped"] == [{
            "task": "app.tasks.invisible", "interval_s": 60.0,
            "reason": "no_metric_label_recorded",
            "matched_emitted": None, "matched_delivered": None,
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


class _PrefixRedis(_Redis):
    """``_Redis`` with a ``keys()`` that honours its GLOB, not just a prefix.

    The parent's ``keys()`` synthesises a metrics-shaped answer and ignores what
    it was asked for, which is fine for the reader it was written for and
    useless for a second key family. A fake that cannot express the question
    cannot answer it — LAT-P039's `M19` survived here for exactly that reason.

    ``fnmatch`` rather than a ``startswith`` on the leading literal, because the
    bucket readers ask for ``prefix:*:b1234`` — a glob with the wildcard in the
    MIDDLE. A prefix-only fake would return every bucket of every age, the
    reader would then filter them itself, and the test would be grading the
    reader's filter against a fake that had already agreed with it.
    """

    def keys(self, pattern):
        import fnmatch

        return [k.encode() for k in self.strings if fnmatch.fnmatchcase(k, pattern)]


@pytest.fixture
def prefix_fake(monkeypatch):
    r = _PrefixRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    return r


class TestMatchedBucketStorage:
    """LAT-P238 / CERT-1966: both sides count into the SAME wall-clock bucket.

    The first version put emissions in a 24h ``_bump_window_counter`` key and
    compared its rate against the 24h delivery counter's. That was blocked: the
    emission counter is born at the deploy while the delivery counter
    deliberately holds up to a day of PRE-deploy history, so the quotient cannot
    tell a healthy current hour from one losing half its fires. These check the
    storage half of the repair — that the two counts really do land in one
    shared, short-lived, clock-derived bucket.
    """

    TASK = "app.tasks.prewarm_live_feed_shapes"

    def _ekey(self, bucket):
        return f"{redis_state.TASK_EMISSION_BUCKET_PREFIX}:{self.TASK}:b{bucket}"

    def _dkey(self, bucket):
        return f"{redis_state.TASK_DELIVERY_BUCKET_PREFIX}:{self.TASK}:b{bucket}"

    def test_the_bucket_index_is_a_pure_function_of_the_clock(self):
        # This is what makes the two counts a matched cohort with no
        # coordination between the beat dyno and the worker dynos: they are not
        # agreeing on a window, they are both reading the same one off the
        # clock. A bucket index derived from anything process-local — a first
        # write, a boot time — would silently give each dyno its own window.
        b = redis_state.EMIT_BUCKET_S
        assert redis_state.emit_bucket_index(0) == 0
        assert redis_state.emit_bucket_index(b - 1) == 0
        assert redis_state.emit_bucket_index(b) == 1
        assert redis_state.emit_bucket_index(3 * b + 5) == 3

    def test_both_writers_land_in_the_same_bucket(self, prefix_fake):
        redis_state.record_task_emission(self.TASK)
        redis_state.record_task_delivery_bucket(self.TASK)
        bucket = redis_state.emit_bucket_index()
        assert prefix_fake.strings[self._ekey(bucket)] == b"1"
        assert prefix_fake.strings[self._dkey(bucket)] == b"1"

    def test_a_bucket_expires_long_before_it_could_hold_old_behaviour(self, prefix_fake):
        # The TTL is the repair. A bucket that outlived its retention would
        # start contributing exactly the history the design exists to exclude.
        redis_state.record_task_emission(self.TASK)
        ttl = prefix_fake.ttls[self._ekey(redis_state.emit_bucket_index())]
        assert ttl == redis_state.EMIT_BUCKET_S * redis_state.EMIT_BUCKET_RETAINED
        assert ttl < 3600, "a bucket must not be able to span a deploy boundary"

    def test_later_writes_do_not_slide_the_bucket_expiry(self, prefix_fake):
        redis_state.record_task_emission(self.TASK)
        key = self._ekey(redis_state.emit_bucket_index())
        prefix_fake.ttls[key] = 60
        redis_state.record_task_emission(self.TASK)
        assert prefix_fake.strings[key] == b"2"
        assert prefix_fake.ttls[key] == 60

    def test_an_empty_name_writes_nothing(self, prefix_fake):
        redis_state.record_task_emission("")
        redis_state.record_task_emission(None)
        redis_state.record_task_delivery_bucket("")
        assert prefix_fake.strings == {}

    def test_the_writers_survive_a_dead_redis(self, monkeypatch):
        def _boom():
            raise RuntimeError("redis down")
        monkeypatch.setattr(redis_state, "get_redis_client", _boom)
        redis_state.record_task_emission("app.tasks.foo")       # must not raise
        redis_state.record_task_delivery_bucket("app.tasks.foo")
        assert redis_state.get_matched_emit_delivery() == {}

    def test_bucket_keys_are_not_read_back_as_phantom_tasks(self, prefix_fake):
        redis_state.record_task_emission(self.TASK)
        redis_state.record_task_delivery_bucket(self.TASK)
        for prefix in (redis_state.TASK_EMISSION_BUCKET_PREFIX,
                       redis_state.TASK_DELIVERY_BUCKET_PREFIX):
            assert not prefix.startswith(f"{TASK_METRICS_PREFIX}:")
        assert [m.get("task") for m in redis_state.get_all_task_metrics()] == []


class TestMatchedBucketReader:
    """Only a COMPLETE bucket is read, and unknown never renders as zero."""

    TASK = "app.tasks.prewarm_live_feed_shapes"
    #: An arbitrary fixed clock. Bucket 2000 is complete; 2001 is filling.
    NOW = 2001 * redis_state.EMIT_BUCKET_S + 42

    def _seed(self, fake, bucket, emitted=None, delivered=None, alive=True):
        if emitted is not None:
            fake.strings[
                f"{redis_state.TASK_EMISSION_BUCKET_PREFIX}:{self.TASK}:b{bucket}"
            ] = str(emitted).encode()
        if delivered is not None:
            fake.strings[
                f"{redis_state.TASK_DELIVERY_BUCKET_PREFIX}:{self.TASK}:b{bucket}"
            ] = str(delivered).encode()
        if alive:
            fake.strings[redis_state.delivery_writer_alive_key(bucket)] = b"1"

    def test_the_last_complete_bucket_is_the_one_returned(self, prefix_fake):
        self._seed(prefix_fake, 2000, emitted=15, delivered=7)
        self._seed(prefix_fake, 2001, emitted=3, delivered=0)   # still filling
        out = redis_state.get_matched_emit_delivery(self.NOW)
        assert out[self.TASK]["emitted"] == 15
        assert out[self.TASK]["delivered"] == 7
        assert out[self.TASK]["bucket_s"] == redis_state.EMIT_BUCKET_S
        assert out[self.TASK]["bucket_start"] == 2000 * redis_state.EMIT_BUCKET_S

    def test_the_filling_bucket_is_never_read(self, prefix_fake):
        # It is not merely partial, it is ASYMMETRICALLY partial: a message
        # published at second 599 is delivered in the next bucket, so the open
        # bucket systematically understates deliveries and would report a
        # permanent phantom loss on every healthy task in the schedule.
        self._seed(prefix_fake, 2001, emitted=3, delivered=0)
        assert redis_state.get_matched_emit_delivery(self.NOW) == {}

    def test_an_older_bucket_is_not_read_either(self, prefix_fake):
        self._seed(prefix_fake, 1999, emitted=99, delivered=1)
        assert redis_state.get_matched_emit_delivery(self.NOW) == {}

    def test_a_missing_delivery_key_is_zero_when_the_writer_is_alive(self, prefix_fake):
        # The reading this instrument most needs to be able to make: 15 fires
        # published, none delivered. A per-task liveness marker could never
        # report it, because a totally-dead task has no per-task delivery key
        # BY DEFINITION.
        self._seed(prefix_fake, 2000, emitted=15, alive=True)
        assert redis_state.get_matched_emit_delivery(self.NOW)[self.TASK][
            "delivered"] == 0

    def test_a_missing_delivery_key_is_unknown_when_the_writer_is_not(self, prefix_fake):
        # The state of the whole fleet for one bucket after the release that
        # ships the bucketed delivery writer. Reading it as 0 would report 100%
        # broker loss on every beat in the schedule at the exact moment the
        # instrument is first trusted.
        self._seed(prefix_fake, 2000, emitted=15, alive=False)
        assert redis_state.get_matched_emit_delivery(self.NOW)[self.TASK][
            "delivered"] is None

    def test_the_liveness_marker_is_written_by_the_real_delivery_writer(self, prefix_fake):
        key = redis_state.delivery_writer_alive_key(redis_state.emit_bucket_index())
        assert key not in prefix_fake.strings
        redis_state.record_task_delivery_bucket("app.tasks.anything_at_all")
        assert key in prefix_fake.strings
        assert prefix_fake.ttls[key] == (
            redis_state.EMIT_BUCKET_S * redis_state.EMIT_BUCKET_RETAINED)

    def test_the_emit_writer_does_not_vouch_for_the_delivery_writer(self, prefix_fake):
        # They run in different dynos and are released independently. If the
        # publish signal could set the marker, a beat dyno on the new release
        # would certify a worker fleet that is still on the old one — and every
        # task would read 100% loss.
        redis_state.record_task_emission("app.tasks.anything_at_all")
        assert not [k for k in prefix_fake.strings
                    if k.startswith(redis_state.TASK_DELIVERY_WRITER_ALIVE_PREFIX)]

    # --- CERT-1968: the proof may not outlive the bucket it vouches for ------

    def _writer_runs_in_bucket(self, monkeypatch, bucket, task="app.tasks.other"):
        """Drive the REAL delivery writer with the clock inside ``bucket``.

        Hand-seeding the marker would not reproduce anything: a mutant that
        writes and reads the proof under a DIFFERENT key still returns "no
        proof" against a hand-seeded correct-shaped key, so the test would pass
        against the very defect it is named for. Faking the clock and letting
        the writer choose its own key is what makes the writer's scoping — not
        the test's idea of it — the thing under test.
        """
        # `monkeypatch.context()`, NOT `monkeypatch.undo()`: the two share one
        # fixture instance with `prefix_fake`, so an undo here would also revert
        # the fake Redis and the reader below would talk to a real client.
        with monkeypatch.context() as m:
            m.setattr(redis_state.time, "time",
                      lambda: bucket * redis_state.EMIT_BUCKET_S + 1)
            redis_state.record_task_delivery_bucket(task)

    def test_liveness_in_a_LATER_bucket_leaves_this_one_unknown(
            self, prefix_fake, monkeypatch):
        # CERT-1968's exact reproduction. 15 publications in bucket N, no
        # bucket-N delivery counter, and the delivery writer's first bucketed
        # write landing in N+1. The blocked version's marker was one global key
        # with a 1,800s TTL, so it was present when N was read: N returned
        # `delivered: 0` and 100% broker loss, when the truth is that the old
        # worker code may have delivered all 15 without the counter existing.
        self._seed(prefix_fake, 2000, emitted=15, alive=False)
        self._writer_runs_in_bucket(monkeypatch, 2001)
        assert redis_state.get_matched_emit_delivery(self.NOW)[self.TASK][
            "delivered"] is None

    def test_liveness_in_THIS_bucket_makes_a_missing_key_a_real_zero(
            self, prefix_fake, monkeypatch):
        # The mirror, and the reading the instrument exists for: the writer WAS
        # running in this bucket and this task still got nothing.
        self._seed(prefix_fake, 2000, emitted=15, alive=False)
        self._writer_runs_in_bucket(monkeypatch, 2000)
        assert redis_state.get_matched_emit_delivery(self.NOW)[self.TASK][
            "delivered"] == 0

    def test_liveness_in_an_EARLIER_bucket_leaves_this_one_unknown_too(
            self, prefix_fake, monkeypatch):
        # The other direction: a writer that STOPPED. A proof scoped to N-1 says
        # nothing about N, and treating it as one would accuse the broker of
        # discarding messages a dead worker was never there to take.
        self._seed(prefix_fake, 2000, emitted=15, alive=False)
        self._writer_runs_in_bucket(monkeypatch, 1999)
        assert redis_state.get_matched_emit_delivery(self.NOW)[self.TASK][
            "delivered"] is None

    def test_the_liveness_marker_is_not_read_back_as_a_task(self, prefix_fake):
        # Scoping the marker by bucket means appending `:bN` — and
        # `bainluck:task_deliv_bucket:__x__:bN` would match the delivery scan's
        # own `bainluck:task_deliv_bucket:*:bN` glob, putting a task called
        # `__writer_alive__` on the health surface. Hence its own top-level
        # prefix; asserted rather than trusted.
        redis_state.record_task_delivery_bucket(self.TASK)
        now = (redis_state.emit_bucket_index() + 1) * redis_state.EMIT_BUCKET_S + 1
        assert set(redis_state.get_matched_emit_delivery(now)) == {self.TASK}

    def test_a_delivery_only_task_is_still_reported(self, prefix_fake):
        self._seed(prefix_fake, 2000, delivered=7)
        row = redis_state.get_matched_emit_delivery(self.NOW)[self.TASK]
        assert row["emitted"] == 0 and row["delivered"] == 7

    def test_a_non_numeric_value_is_skipped_not_zeroed(self, prefix_fake):
        prefix_fake.strings[
            f"{redis_state.TASK_EMISSION_BUCKET_PREFIX}:app.tasks.bad:b2000"] = b"x"
        self._seed(prefix_fake, 2000, emitted=15, delivered=15)
        out = redis_state.get_matched_emit_delivery(self.NOW)
        assert "app.tasks.bad" not in out
        assert out[self.TASK]["emitted"] == 15


class TestPublishSignalPayloadShape:
    """The message-shape half: what ``before_task_publish`` actually hands over.

    Split out and made pure because the signal block itself needs a live celery
    publish to exercise and is therefore `pragma: no cover`, while THIS is the
    part that can silently be wrong. ``task_prerun`` passes the task OBJECT as
    ``sender``; ``before_task_publish`` passes the task NAME as a string. Three
    handlers in the same file read ``sender.name``, so copying that shape here
    would have produced a counter that reads zero for every task — which does
    not look like a bug, it looks like a finding.
    """

    def test_a_string_sender_is_the_name(self):
        assert _published_task_name("app.tasks.foo", None, None) == "app.tasks.foo"

    def test_protocol_2_headers_carry_the_name(self):
        assert _published_task_name(
            None, {"task": "app.tasks.foo"}, None) == "app.tasks.foo"

    def test_protocol_1_body_carries_the_name(self):
        assert _published_task_name(
            None, None, {"task": "app.tasks.foo"}) == "app.tasks.foo"

    def test_an_object_sender_still_yields_its_name(self):

        class _Task:
            name = "app.tasks.foo"
        assert _published_task_name(_Task(), None, None) == "app.tasks.foo"

    def test_an_unreadable_publication_is_none_not_a_blank_key(self):
        assert _published_task_name(None, None, None) is None
        assert _published_task_name(object(), {}, {}) is None
        assert _published_task_name("", {}, {}) is None

    def test_a_retry_is_filtered_exactly_as_it_is_on_the_delivery_side(self):
        assert _published_retries({"retries": 2}, None) == 2
        assert _published_retries(None, {"retries": 1}) == 1

    def test_a_first_attempt_reads_zero(self):
        assert _published_retries({"retries": 0}, None) == 0

    def test_an_unreadable_retry_count_defaults_to_counting_it(self):
        # The same call `_record_delivery` makes one signal up: losing the count
        # is worse than an upper bound. And the two sides must default the SAME
        # way — an unreadable message counted as published but not as delivered
        # would present as broker loss that never happened.
        assert _published_retries(None, None) == 0
        assert _published_retries({"retries": "many"}, None) == 0
        assert _published_retries({}, {}) == 0


class TestMatchedPairReachesTheGrader:
    SCHED = {"b": {"task": "app.tasks.foo", "schedule": 40.0}}

    def _call(self, matched=None):
        return build_schedule_adherence(
            self.SCHED,
            [_metrics("foo", starts=1080, window_s=86400.0)],
            {"app.tasks.foo": "foo"},
            {"app.tasks.foo": {"fires": 1080, "window_s": 86400.0}},
            matched=matched,
        )

    def test_the_row_carries_the_pair_and_the_span_it_covers(self):
        out = self._call({"app.tasks.foo": {
            "emitted": 15, "delivered": 7, "bucket_s": 600,
            "bucket_start": 1_757_100_000.0, "coverage_proven": True}})
        row = out["all"]["app.tasks.foo"]
        assert row["matched_emitted"] == 15
        assert row["matched_delivered"] == 7
        assert row["matched_bucket_s"] == 600
        assert row["matched_bucket_start"] == 1_757_100_000.0
        assert row["undelivered_fraction"] == pytest.approx(8 / 15, abs=0.005)
        assert "never reached a worker" in row["reason"]

    def test_the_24h_delivery_counter_is_not_the_matched_one(self):
        # The join must not quietly reuse `deliveries` as the denominator's
        # partner. Same 24h counters on both calls; only the bucket differs, and
        # the diagnosis must follow the bucket.
        broken = self._call({"app.tasks.foo": {
            "emitted": 15, "delivered": 7, "bucket_s": 600, "bucket_start": 1.0, "coverage_proven": True}})
        healthy = self._call({"app.tasks.foo": {
            "emitted": 15, "delivered": 15, "bucket_s": 600, "bucket_start": 1.0, "coverage_proven": True}})
        assert broken["all"]["app.tasks.foo"]["deliveries"] == \
               healthy["all"]["app.tasks.foo"]["deliveries"] == 1080
        assert broken["all"]["app.tasks.foo"]["undelivered_fraction"] != \
               healthy["all"]["app.tasks.foo"]["undelivered_fraction"]

    def test_no_matched_argument_leaves_the_fraction_unknown(self):
        row = self._call()["all"]["app.tasks.foo"]
        assert row["undelivered_fraction"] is None
        assert row["matched_emitted"] is None and row["matched_delivered"] is None

    def test_the_pair_needs_no_label_join(self):
        out = build_schedule_adherence(
            self.SCHED, [], {},
            {"app.tasks.foo": {"fires": 1080, "window_s": 86400.0}},
            matched={"app.tasks.foo": {
                "emitted": 15, "delivered": 7, "bucket_s": 600,
                "bucket_start": 1.0, "coverage_proven": True}},
        )
        assert out["graded"] == 1
        assert out["all"]["app.tasks.foo"]["matched_emitted"] == 15

    def test_publications_alone_stay_unmapped_but_carry_their_counts(self):
        # "Beat is publishing into a void": nothing ran, nothing was delivered,
        # and the bucket pair is the only witness. Not graded — a publication is
        # not evidence anything ran — but not dropped either.
        out = build_schedule_adherence(
            self.SCHED, [], {}, {},
            matched={"app.tasks.foo": {
                "emitted": 15, "delivered": 0, "bucket_s": 600,
                "bucket_start": 1.0, "coverage_proven": True}},
        )
        assert out["graded"] == 0
        assert out["unmapped"] == [{
            "task": "app.tasks.foo", "interval_s": 40.0,
            "reason": "no_metric_label_recorded",
            "matched_emitted": 15, "matched_delivered": 0,
        }]

    def test_a_matched_pair_for_an_unscheduled_task_is_ignored(self):
        out = build_schedule_adherence(
            {}, [], {}, {},
            matched={"app.tasks.manual": {
                "emitted": 3, "delivered": 3, "bucket_s": 600,
                "bucket_start": 1.0, "coverage_proven": True}},
        )
        assert out["scheduled_tasks"] == 0
        assert out["all"] == {} and out["unmapped"] == []


class TestTheSignalsActuallyFire:
    """End to end, against a real celery publish and a real prerun: are the
    counters WRITTEN, and do they land in the SAME bucket?

    Every test above proves the pieces are correct in isolation, and none of
    them would fail if the signals never reached their handlers at all — a dead
    instrument reads exactly like a healthy beat, because both produce a counter
    that does not move.

    ``memory://`` is kombu's in-process transport, so ``apply_async`` performs a
    genuine publish through the same ``send_task_message`` path production uses.
    The handlers under test are the module-level ones connected at
    ``import app.tasks``; nothing here re-declares them.
    """

    @pytest.fixture
    def probe_app(self):
        from celery import Celery

        app = Celery("lat_p238_probe", broker="memory://", backend=None)

        @app.task(name="app.tasks.lat_p238_probe")
        def _probe():  # pragma: no cover - never executed, only published
            return 1

        return app, _probe

    def test_a_real_publish_increments_the_current_bucket(self, prefix_fake, probe_app):
        # Importing the module is what connects the handler; `tasks_mod` is
        # imported once at the top of this file so the same module object is
        # used everywhere (CodeQL py/import-and-import-from).
        _app, probe = probe_app
        bucket = redis_state.emit_bucket_index()
        key = (f"{redis_state.TASK_EMISSION_BUCKET_PREFIX}"
               f":app.tasks.lat_p238_probe:b{bucket}")
        assert key not in prefix_fake.strings
        probe.apply_async()
        assert prefix_fake.strings[key] == b"1"

    def test_a_real_retry_publish_is_not_counted(self, prefix_fake, probe_app):
        _app, probe = probe_app
        bucket = redis_state.emit_bucket_index()
        key = (f"{redis_state.TASK_EMISSION_BUCKET_PREFIX}"
               f":app.tasks.lat_p238_probe:b{bucket}")
        probe.apply_async()
        probe.apply_async(retries=3)
        assert prefix_fake.strings[key] == b"1"

    def test_the_publish_survives_a_dead_redis(self, monkeypatch, probe_app):
        # The instrument must never be the reason a publication fails — least
        # of all here, where the publisher is celery beat and a raise would take
        # out the scheduler this counter exists to grade.
        def _boom(*_a, **_k):
            raise RuntimeError("redis down")
        monkeypatch.setattr(redis_state, "get_redis_client", _boom)
        _app, probe = probe_app
        probe.apply_async()  # must not raise

    def test_a_publish_and_a_prerun_land_in_one_readable_cohort(self, prefix_fake):
        # THE WHOLE REPAIR, end to end and through both real handlers: publish
        # three, deliver two, and read back a matched pair that says so. If the
        # two writers ever disagree about the bucket index — different clock,
        # different rounding, a process-local epoch — this is what catches it,
        # and nothing else would: each side would still look perfect alone.
        for _ in range(3):
            tasks_mod._record_emission(sender="app.tasks.probe_pair", headers={})
        for _ in range(2):
            redis_state.record_task_delivery_bucket("app.tasks.probe_pair")

        # Read from inside the NEXT bucket, so the one just written is complete.
        now = (redis_state.emit_bucket_index() + 1) * redis_state.EMIT_BUCKET_S + 1
        row = redis_state.get_matched_emit_delivery(now)["app.tasks.probe_pair"]
        assert row["emitted"] == 3 and row["delivered"] == 2
        assert row["bucket_s"] == redis_state.EMIT_BUCKET_S


class TestCoverageProofNeedsBothSidesAndTheBucketBefore:
    """CERT-1972 storage half: what proves a bucket was fully observed.

    ``writer_alive`` (CERT-1968) answers "was the delivery writer running during
    N?", which is the zero-versus-unknown question. ``coverage_proven`` answers
    the strictly harder one the EXPECTATION comparison needs: did both counters
    cover the whole of N, or only a suffix of it? A publisher that activates at
    second 300 of a 600s bucket publishes 7 fires at a perfect 40s cadence and
    the bucket expects 15.
    """

    TASK = "app.tasks.prewarm_live_feed_shapes"
    NOW = 2001 * redis_state.EMIT_BUCKET_S + 42

    def _writer_runs_in(self, monkeypatch, bucket, deliveries=True, emissions=True):
        with monkeypatch.context() as m:
            m.setattr(redis_state.time, "time",
                      lambda: bucket * redis_state.EMIT_BUCKET_S + 1)
            if emissions:
                redis_state.record_task_emission(self.TASK)
            if deliveries:
                redis_state.record_task_delivery_bucket(self.TASK)

    def _row(self):
        return redis_state.get_matched_emit_delivery(self.NOW)[self.TASK]

    def test_both_writers_in_this_bucket_and_the_one_before_is_proof(self, prefix_fake, monkeypatch):
        self._writer_runs_in(monkeypatch, 1999)
        self._writer_runs_in(monkeypatch, 2000)
        assert self._row()["coverage_proven"] is True

    def test_a_publisher_that_activated_inside_this_bucket_is_not_proof(self, prefix_fake, monkeypatch):
        # THE BLOCK'S CASE. Deliveries instrumented throughout; the publisher's
        # first bucketed write is in N itself, so its count covers a suffix of
        # the bucket and cannot be compared against the bucket's expectation.
        self._writer_runs_in(monkeypatch, 1999, emissions=False)
        self._writer_runs_in(monkeypatch, 2000)
        row = self._row()
        assert row["coverage_proven"] is False
        # ...and the weaker flag still holds, so `delivered` is a real number.
        assert row["delivered"] is not None

    def test_a_delivery_writer_that_activated_inside_this_bucket_is_not_proof(self, prefix_fake, monkeypatch):
        # The mirror, which produces a FALSE ACCUSATION rather than a false
        # exoneration and is therefore the worse of the two.
        self._writer_runs_in(monkeypatch, 1999, deliveries=False)
        self._writer_runs_in(monkeypatch, 2000)
        assert self._row()["coverage_proven"] is False

    def test_a_writer_absent_from_this_bucket_is_not_proof_either(self, prefix_fake, monkeypatch):
        # Present in N-1, gone in N: a dyno that died. Coverage of N is not
        # established by having covered the bucket before it.
        self._writer_runs_in(monkeypatch, 1999)
        self._writer_runs_in(monkeypatch, 2000, emissions=False)
        assert self._row()["coverage_proven"] is False

    def test_coverage_is_false_when_nothing_is_instrumented(self, prefix_fake):
        self._seed_bare(prefix_fake)
        assert self._row()["coverage_proven"] is False

    def _seed_bare(self, fake):
        fake.strings[
            f"{redis_state.TASK_EMISSION_BUCKET_PREFIX}:{self.TASK}:b2000"] = b"7"

    def test_the_two_markers_have_different_prefixes(self, prefix_fake, monkeypatch):
        # A single shared marker would be set by whichever writer ran first and
        # would then vouch for the other — which is the CERT-1968 defect with
        # the two sides swapped rather than the two buckets.
        assert (redis_state.TASK_EMIT_WRITER_ALIVE_PREFIX
                != redis_state.TASK_DELIVERY_WRITER_ALIVE_PREFIX)
        self._writer_runs_in(monkeypatch, 2000, deliveries=False)
        assert redis_state.emit_writer_alive_key(2000) in prefix_fake.strings
        assert (redis_state.delivery_writer_alive_key(2000)
                not in prefix_fake.strings)

    def test_neither_marker_is_read_back_as_a_task(self, prefix_fake, monkeypatch):
        self._writer_runs_in(monkeypatch, 1999)
        self._writer_runs_in(monkeypatch, 2000)
        assert set(redis_state.get_matched_emit_delivery(self.NOW)) == {self.TASK}

    def test_the_markers_expire_with_the_buckets_they_vouch_for(self, prefix_fake, monkeypatch):
        self._writer_runs_in(monkeypatch, 2000)
        ttl = redis_state.EMIT_BUCKET_S * redis_state.EMIT_BUCKET_RETAINED
        assert prefix_fake.ttls[redis_state.emit_writer_alive_key(2000)] == ttl
        assert prefix_fake.ttls[redis_state.delivery_writer_alive_key(2000)] == ttl


class TestLeaseDeclineReaderMatchesTheWriter:
    """LAT-P238 ITEM 3: the reader is new; the counter was already correct.

    ``single_flight._record_skip`` has counted declines under
    ``SKIP_COUNTER_PREFIX`` since it shipped, using ``_bump_window_counter``'s
    exact ``SET … NX EX`` idiom. What was missing is the window: the only way to
    read it was ``/api/admin/redis-read``, which returns the VALUE and no TTL,
    so 346 declines could be 346 in eight minutes or 346 in a day.

    These drive the REAL writer — ``single_flight.acquire``'s decline path, not
    a hand-built key — because the failure this class exists to prevent is the
    one where both halves are individually correct and disagree about the key.
    """

    TASK = "app.tasks.poll_all_odds"

    def test_a_real_declined_lease_is_read_back_with_its_window(self, prefix_fake):
        from app.utils.single_flight import (
            SKIP_COUNTER_TTL_SECONDS, acquire, skip_counter_key,
        )

        first = acquire(self.TASK, rc=prefix_fake)
        assert first.acquired          # nobody held it
        second = acquire(self.TASK, rc=prefix_fake)
        assert not second.acquired     # the decline that gets counted

        prefix_fake.ttls[skip_counter_key(self.TASK)] = SKIP_COUNTER_TTL_SECONDS - 900
        out = redis_state.get_all_lease_declines()
        assert out[self.TASK]["declines"] == 1
        assert out[self.TASK]["window_s"] == pytest.approx(900.0)

    def test_the_lease_key_itself_is_not_read_as_a_decline_counter(self, prefix_fake):
        # `SKIP_COUNTER_PREFIX` extends `LEASE_KEY_PREFIX`, so the two key
        # families live in the same namespace and a prefix scan that used the
        # shorter one would report every held lease as a decline count — with
        # a uuid token where the integer belongs.
        from app.utils.single_flight import acquire

        acquire(self.TASK, rc=prefix_fake)   # writes the LEASE key only
        assert redis_state.get_all_lease_declines() == {}

    def test_a_counter_with_no_expiry_is_unmeasurable_not_fresh(self, prefix_fake):
        from app.utils.single_flight import skip_counter_key

        prefix_fake.strings[skip_counter_key(self.TASK)] = b"346"
        out = redis_state.get_all_lease_declines()
        assert out[self.TASK] == {"declines": 346, "window_s": None}

    def test_a_dead_redis_reads_empty_rather_than_raising(self, monkeypatch):
        def _boom():
            raise RuntimeError("redis down")
        monkeypatch.setattr(redis_state, "get_redis_client", _boom)
        assert redis_state.get_all_lease_declines() == {}

    def test_the_ttl_the_reader_ages_against_is_the_one_the_writer_stamps(self):
        # `_window_age_s` derives `age = WINDOW_COUNTER_TTL - ttl` against a
        # constant of its own. The skip counter is written under
        # `SKIP_COUNTER_TTL_SECONDS`, a different constant in a different file.
        # They are equal today and the reader is only correct while they are —
        # if one moves, every decline window silently reads as an offset rather
        # than an age, which looks like data rather than a bug.
        from app.utils.single_flight import SKIP_COUNTER_TTL_SECONDS
        assert SKIP_COUNTER_TTL_SECONDS == redis_state.WINDOW_COUNTER_TTL

    def test_the_row_carries_the_count_and_the_window(self):
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.poll_all_odds", "schedule": 30.0}},
            [_metrics("poll_odds", starts=1400, window_s=86400.0)],
            {"app.tasks.poll_all_odds": "poll_odds"},
            {"app.tasks.poll_all_odds": {"fires": 2880, "window_s": 86400.0}},
            lease_declines={
                "app.tasks.poll_all_odds": {"declines": 900, "window_s": 86400.0},
            },
        )
        row = out["all"]["app.tasks.poll_all_odds"]
        assert row["lease_declines"] == 900
        assert row["lease_declines_window_s"] == 86400.0
        # And the superset it splits is still whole and still published.
        assert row["self_gated_fires"] == 1480

    def test_declines_need_no_label_join_either(self):
        # `single_flight` is called with the fully-qualified celery name, so a
        # task invisible to the label map still gets its declines.
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.poll_all_odds", "schedule": 30.0}}, [], {},
            {"app.tasks.poll_all_odds": {"fires": 2880, "window_s": 86400.0}},
            lease_declines={
                "app.tasks.poll_all_odds": {"declines": 900, "window_s": 86400.0},
            },
        )
        assert out["all"]["app.tasks.poll_all_odds"]["lease_declines"] == 900

    def test_no_lease_declines_argument_leaves_both_fields_unknown(self):
        out = build_schedule_adherence(
            {"b": {"task": "app.tasks.foo", "schedule": 30.0}},
            [_metrics("foo", starts=2880, window_s=86400.0)],
            {"app.tasks.foo": "foo"},
        )
        row = out["all"]["app.tasks.foo"]
        assert row["lease_declines"] is None
        assert row["lease_declines_window_s"] is None


def _adherence_request():
    """A Request carrying the admin bearer token the route actually requires."""
    from starlette.requests import Request

    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/admin/celery/schedule-adherence",
        "headers": [(b"authorization", b"Bearer test-admin-token")],
        "query_string": b"",
    })


class TestEndpointToReaderWiring:
    """LAT-P238-LEASE-ENDPOINT-WIRING-GUARD — the handoff above the builder.

    ``TestRouteJoin`` and the lease tests above prove the BUILDER places each
    argument correctly, and the reader tests prove ``get_all_lease_declines``
    reads Redis correctly. Neither covers the six lines that hand one to the
    other, and that gap is the whole defect class: the route calls
    ``build_schedule_adherence`` with four positional arguments and two keyword
    arguments, every one of which defaults to ``None``/``{}``.

    So dropping ``lease_declines=`` — or crossing it with ``matched=`` — raises
    nothing, fails no existing test, and publishes ``lease_declines: null`` on
    all 140 rows. That is indistinguishable from "no task has ever declined a
    lease", which is the reading a healthy fleet produces. Both ends stay green
    while the field is dead, so the assertion has to be made HERE, on the join,
    with a value that could only have come from its own reader.

    Every sentinel below is a distinct integer for that reason: a swap of any
    two readers moves a number to a field that does not expect it, and the
    equality assertions catch it. Values that merely looked plausible in every
    slot would agree with a crossed wiring by construction.
    """

    TASK = "app.tasks.foo"

    def _run(self, monkeypatch, *, lease_declines=None, matched=None):
        import asyncio

        from app.routes import admin_celery
        from app.tasks import celery_app

        monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
        monkeypatch.setattr(
            celery_app.conf, "beat_schedule",
            {"b": {"task": self.TASK, "schedule": 60.0}}, raising=False,
        )
        monkeypatch.setattr(
            redis_state, "get_all_task_metrics",
            lambda: [_metrics("foo", starts=10, window_s=3600)],
        )
        monkeypatch.setattr(
            redis_state, "get_task_label_map", lambda: {self.TASK: "foo"},
        )
        monkeypatch.setattr(
            redis_state, "get_all_task_deliveries",
            lambda: {self.TASK: {"fires": 11, "window_s": 1100.0}},
        )
        monkeypatch.setattr(
            redis_state, "get_matched_emit_delivery",
            lambda: matched if matched is not None else {self.TASK: {
                "emitted": 22, "delivered": 13, "bucket_s": 600,
                "bucket_start": 1788000000.0, "coverage_proven": True,
            }},
        )
        monkeypatch.setattr(
            redis_state, "get_all_lease_declines",
            lambda: lease_declines if lease_declines is not None else {
                self.TASK: {"declines": 33, "window_s": 3300.0},
            },
        )
        out = asyncio.run(
            admin_celery.celery_schedule_adherence(_adherence_request())
        )
        return out["all"][self.TASK]

    def test_every_reader_lands_in_its_own_field(self, monkeypatch):
        row = self._run(monkeypatch)
        assert row["deliveries"] == 11
        assert row["deliveries_window_s"] == 1100.0
        assert row["matched_emitted"] == 22
        assert row["matched_delivered"] == 13
        assert row["matched_bucket_s"] == 600
        assert row["matched_coverage_proven"] is True
        # The two the follow-up is actually about.
        assert row["lease_declines"] == 33
        assert row["lease_declines_window_s"] == 3300.0

    def test_the_lease_reader_is_reached_at_all(self, monkeypatch):
        """The narrow regression: an unpassed reader reads None, not 33.

        Asserted against a reader that RETURNS data, because the failure being
        guarded is silent — a dropped keyword argument and an empty fleet
        produce the same payload.
        """
        assert self._run(monkeypatch)["lease_declines"] == 33
        assert self._run(monkeypatch, lease_declines={})["lease_declines"] is None

    def test_lease_declines_is_not_crossed_with_the_matched_pair(self, monkeypatch):
        """The two keyword arguments sit adjacent and both key by celery name.

        Nothing about their shapes stops one being passed where the other
        belongs, so the join is pinned rather than assumed.
        """
        row = self._run(monkeypatch)
        assert row["lease_declines"] != row["matched_emitted"]
        assert row["lease_declines"] != row["matched_delivered"]
        # A crossed wiring would read `declines`/`window_s` off the matched dict
        # and find neither, i.e. silently None.
        row = self._run(
            monkeypatch,
            matched={self.TASK: {"declines": 33, "window_s": 3300.0}},
        )
        assert row["matched_emitted"] is None
        assert row["lease_declines"] == 33
