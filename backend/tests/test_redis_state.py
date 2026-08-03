"""Tests for redis_state.py helper functions.

Covers:
- compute_odds_hash: deterministic hashing of odds data for change detection
- Task metrics: module-level constants and import validation
"""

import inspect

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import (
    compute_odds_hash,
    get_odds_api_quota,
    TASK_METRICS_PREFIX,
    TASK_METRICS_TTL,
    _utc_now_iso,
)


def _make_event(event_id="evt1", bookmaker="fanduel", price=-150, point=None):
    """Create a minimal Odds API event structure."""
    outcome = {"name": "Home", "price": price}
    if point is not None:
        outcome["point"] = point
    return {
        "id": event_id,
        "bookmakers": [{
            "key": bookmaker,
            "markets": [{
                "key": "h2h",
                "outcomes": [outcome],
            }],
        }],
    }


class TestComputeOddsHash:
    """Tests for deterministic odds data hashing."""

    def test_deterministic_same_input(self):
        """Same input should always produce the same hash."""
        events = [_make_event()]
        assert compute_odds_hash(events) == compute_odds_hash(events)

    def test_different_price_different_hash(self):
        h1 = compute_odds_hash([_make_event(price=-150)])
        h2 = compute_odds_hash([_make_event(price=-160)])
        assert h1 != h2

    def test_different_bookmaker_different_hash(self):
        h1 = compute_odds_hash([_make_event(bookmaker="fanduel")])
        h2 = compute_odds_hash([_make_event(bookmaker="draftkings")])
        assert h1 != h2

    def test_different_event_id_different_hash(self):
        h1 = compute_odds_hash([_make_event(event_id="evt1")])
        h2 = compute_odds_hash([_make_event(event_id="evt2")])
        assert h1 != h2

    def test_empty_list(self):
        """Empty events list should still produce a valid hash."""
        h = compute_odds_hash([])
        assert isinstance(h, str)
        assert len(h) == 32  # MD5 hex digest length

    def test_event_order_independent(self):
        """Hash should be the same regardless of event order in the list."""
        e1 = _make_event(event_id="a", price=-100)
        e2 = _make_event(event_id="b", price=-200)
        h_forward = compute_odds_hash([e1, e2])
        h_reverse = compute_odds_hash([e2, e1])
        assert h_forward == h_reverse

    def test_returns_md5_hex_string(self):
        h = compute_odds_hash([_make_event()])
        assert isinstance(h, str)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_with_point_spread(self):
        """Events with point spreads should hash differently from those without."""
        h_no_point = compute_odds_hash([_make_event(point=None)])
        h_with_point = compute_odds_hash([_make_event(point=-3.5)])
        assert h_no_point != h_with_point

    def test_no_bookmakers_key(self):
        """Events without bookmakers should produce a valid hash."""
        h = compute_odds_hash([{"id": "evt1"}])
        assert isinstance(h, str)
        assert len(h) == 32


class TestTaskMetricsConstants:
    """Test task metrics configuration constants."""

    def test_prefix_format(self):
        assert TASK_METRICS_PREFIX == "bainluck:task_metrics"

    def test_ttl_is_48_hours(self):
        assert TASK_METRICS_TTL == 172800  # 48 hours

    def test_utc_now_iso_format(self):
        """_utc_now_iso returns a valid ISO timestamp."""
        result = _utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result
        # Should be parseable
        from datetime import datetime
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_imports_exist(self):
        """Verify all metrics functions are importable."""
        from app.tasks.redis_state import (
            record_task_success,
            record_task_failure,
            get_task_metrics,
            get_all_task_metrics,
        )
        # Functions exist and are callable
        assert callable(record_task_success)
        assert callable(record_task_failure)
        assert callable(get_task_metrics)
        assert callable(get_all_task_metrics)


class _FakeMetricsRedis:
    """Fake redis backing get_task_metrics: hash per task + counter keys."""

    def __init__(self, hashes, counters=None):
        # hashes: {task_name: {b"consecutive_failures": b"3", ...}}
        self.hashes = hashes
        self.counters = counters or {}
        self.calls = []

    # --- read side ---------------------------------------------------------
    def hgetall(self, key):
        # key = "bainluck:task_metrics:<task_name>"
        task = key.rsplit(":", 1)[-1]
        return self.hashes.get(task, {})

    def get(self, key):
        return self.counters.get(key)

    def hget(self, key, field):
        task = key.rsplit(":", 1)[-1]
        return self.hashes.get(task, {}).get(field.encode())

    def keys(self, _pattern):
        out = []
        for task in self.hashes:
            out.append(f"{TASK_METRICS_PREFIX}:{task}".encode())
        return out

    # --- write side (pipeline is a no-op recorder) -------------------------
    def pipeline(self):
        return self

    def hset(self, key, mapping=None):
        self.calls.append(("hset", key, dict(mapping or {})))
        task = key.rsplit(":", 1)[-1]
        target = self.hashes.setdefault(task, {})
        for field, value in (mapping or {}).items():
            target[field.encode()] = str(value).encode()

    def expire(self, key, ttl):
        self.calls.append(("expire", key, ttl))

    def set(self, key, value, ex=None, nx=False):
        self.calls.append(("set", key, value, ex, nx))
        if nx and key in self.counters:
            return None
        self.counters[key] = str(value).encode()
        return True

    def incr(self, key):
        self.calls.append(("incr", key))
        self.counters[key] = str(int(self.counters.get(key, b"0")) + 1).encode()

    def execute(self):
        return []


class TestRetiredTaskHealth:
    """A task retired from the beat but kept dormant must not latch the health
    rollups to degraded/critical via stale metrics (#991 / Queue #123 Item 2)."""

    def test_resolve_winners_is_registered_retired(self):
        assert "resolve_winners" in redis_state.RETIRED_TASK_LABELS

    def test_retired_task_reports_retired_not_degraded(self, monkeypatch):
        # consecutive_failures=3 would normally be "degraded"
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis({"resolve_winners": {b"consecutive_failures": b"3"}}),
        )
        result = redis_state.get_task_metrics("resolve_winners")
        assert result["health"] == "retired"
        assert result["retired"] is True

    def test_retired_task_reports_retired_even_when_critical(self, monkeypatch):
        # consecutive_failures=9 would normally be "critical"
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis({"resolve_winners": {b"consecutive_failures": b"9"}}),
        )
        assert redis_state.get_task_metrics("resolve_winners")["health"] == "retired"

    def test_non_retired_task_still_degrades(self, monkeypatch):
        # A RECENT failure keeps failures_24h > 0, so the task is genuinely
        # failing (not idle) and the consecutive-failure bands stay live.
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis(
                {"poll_odds": {b"consecutive_failures": b"3"}},
                counters={f"{TASK_METRICS_PREFIX}:poll_odds:failures": b"3"},
            ),
        )
        result = redis_state.get_task_metrics("poll_odds")
        assert result["health"] == "degraded"
        assert "retired" not in result


class TestIdleHealthMisread:
    """L2-116: a task idle in the last 24h must read `no_data`, not
    critical/degraded, even when a stale `consecutive_failures` lingers in the
    48h-TTL metrics hash after its 24h :failures counter has expired (r195: an
    idle moment scored `critical` — the inverse of a stuck fetch)."""

    def test_idle_task_with_stale_consecutive_failures_is_no_data(self, monkeypatch):
        # consecutive_failures=9 (would be "critical") BUT no successes/failures in
        # the last 24h → the failures aged out; the task is idle, not broken.
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis({"backfill_kalshi_settled": {b"consecutive_failures": b"9"}}),
        )
        result = redis_state.get_task_metrics("backfill_kalshi_settled")
        assert result["health"] == "no_data"

    def test_idle_task_excluded_from_critical_rollup(self, monkeypatch):
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis({"backfill_kalshi_settled": {b"consecutive_failures": b"7"}}),
        )
        tasks = redis_state.get_all_task_metrics()
        critical = [t for t in tasks if t.get("health") == "critical"]
        assert critical == []

    def test_recent_failure_still_critical(self, monkeypatch):
        # Same latched count, but a failure WITHIN 24h → genuinely failing → critical.
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis(
                {"backfill_kalshi_settled": {b"consecutive_failures": b"7"}},
                counters={f"{TASK_METRICS_PREFIX}:backfill_kalshi_settled:failures": b"7"},
            ),
        )
        assert redis_state.get_task_metrics("backfill_kalshi_settled")["health"] == "critical"

    def test_retired_task_excluded_from_degraded_rollup(self, monkeypatch):
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis({
                "resolve_winners": {b"consecutive_failures": b"4"},
                "poll_odds": {b"consecutive_failures": b"0"},
            }),
        )
        tasks = redis_state.get_all_task_metrics()
        degraded = [t for t in tasks if t.get("health") == "degraded"]
        critical = [t for t in tasks if t.get("health") == "critical"]
        assert degraded == []
        assert critical == []
        # the retired task is still surfaced, just not as degraded/critical
        assert any(t.get("task") == "resolve_winners" and t.get("health") == "retired"
                   for t in tasks)


class TestGetRedisClientSocketTimeout:
    """#995 attempt-9: get_redis_client must accept socket timeouts so a
    hot-loop marker client can't freeze the asyncio event loop on a hung Redis.
    Without a bound, the sync setex in poll_kalshi's progress_cb owns the loop
    forever and no wait_for/deadline timer can fire — the residual sync block."""

    def test_socket_timeouts_applied_to_connection_pool(self):
        client = redis_state.get_redis_client(
            socket_timeout=2.0, socket_connect_timeout=2.0
        )
        kwargs = client.connection_pool.connection_kwargs
        assert kwargs.get("socket_timeout") == 2.0
        assert kwargs.get("socket_connect_timeout") == 2.0

    def test_default_is_bounded(self):
        # #969 NEVER-AGAIN: a bare get_redis_client() must be BOUNDED by default
        # so no caller (69 bare calls in tasks/) can freeze the event loop on a
        # hung Redis. Both timeouts default to a finite value.
        client = redis_state.get_redis_client()
        kwargs = client.connection_pool.connection_kwargs
        assert kwargs.get("socket_timeout") == redis_state._DEFAULT_REDIS_SOCKET_TIMEOUT
        assert kwargs.get("socket_connect_timeout") == redis_state._DEFAULT_REDIS_SOCKET_TIMEOUT
        assert kwargs.get("socket_timeout") is not None

    def test_explicit_none_opts_out(self):
        # Deliberate opt-out for a legitimate long blocking op.
        client = redis_state.get_redis_client(
            socket_timeout=None, socket_connect_timeout=None
        )
        kwargs = client.connection_pool.connection_kwargs
        assert kwargs.get("socket_timeout") is None

    def test_signature_exposes_both_timeout_params(self):
        sig = inspect.signature(redis_state.get_redis_client)
        assert "socket_timeout" in sig.parameters
        assert "socket_connect_timeout" in sig.parameters


class TestFastFailRetry:
    """#1197 (r259): LATENCY IS THE GATE. Hot-request-path Redis clients (the
    rate-limiter, the latency sampler) must fail-open FAST on a churning TLS
    connection instead of burning the robust 3-attempt background retry budget
    — the cause of the 7-17.6s warm team-route latency. The fast-fail retry has
    strictly fewer attempts than the background retry."""

    def test_fast_fail_retry_has_fewer_attempts(self):
        fast = redis_state._redis_fast_fail_retry()
        robust = redis_state._redis_retry()
        # redis.retry.Retry stores the retry count on `_retries`.
        assert fast._retries < robust._retries
        assert fast._retries <= 1

    def test_get_redis_client_fast_fail_uses_bounded_retry(self):
        fast_client = redis_state.get_redis_client(socket_timeout=0.5, fast_fail=True)
        robust_client = redis_state.get_redis_client()
        fast_retry = fast_client.connection_pool.connection_kwargs.get("retry")
        robust_retry = robust_client.connection_pool.connection_kwargs.get("retry")
        assert fast_retry is not None and robust_retry is not None
        assert fast_retry._retries < robust_retry._retries
        # socket bound still honored on the fast-fail client.
        assert fast_client.connection_pool.connection_kwargs.get("socket_timeout") == 0.5

    def test_signature_exposes_fast_fail(self):
        sig = inspect.signature(redis_state.get_redis_client)
        assert "fast_fail" in sig.parameters

    def test_rate_limiter_imports_fast_fail_retry(self):
        # The request-path rate limiter must use the fast-fail retry, not the
        # robust background retry (r259).
        import pathlib
        src = pathlib.Path(redis_state.__file__).parent.parent / "utils" / "rate_limit.py"
        text = src.read_text()
        assert "_redis_fast_fail_retry" in text
        assert "socket_timeout" in text


class TestNoUnboundedRawRedisInTasks:
    """#969 NEVER-AGAIN CI guard: tasks/ must NOT construct a raw sync Redis
    client (redis.from_url / redis.Redis) directly — every sync client must come
    from get_redis_client(), which is bounded by default. A raw unbounded client
    in an async task can freeze the event loop (the #995 class)."""

    def test_no_raw_sync_redis_construction_in_tasks(self):
        import pathlib
        import re

        tasks_dir = pathlib.Path(redis_state.__file__).parent
        # redis_state.py is the ONE sanctioned place that calls redis.from_url.
        offenders = []
        pat = re.compile(r"\bredis\.(from_url|Redis)\s*\(")
        for py in tasks_dir.glob("*.py"):
            if py.name == "redis_state.py":
                continue
            text = py.read_text()
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if pat.search(line):
                    offenders.append(f"{py.name}:{i}: {line.strip()}")
        assert not offenders, (
            "raw sync Redis client(s) in tasks/ (use get_redis_client(), bounded "
            "by default):\n" + "\n".join(offenders)
        )

    def test_no_raw_redis_construction_in_routes_and_services(self):
        """#1197 CI guard: routes/ and services/ must NOT construct a raw Redis
        client (redis.from_url / redis.Redis / aioredis.from_url) directly — every
        client must come from the bounded, retry-wrapped helpers so a Heroku Redis
        TLS-handshake blip degrades (retry) instead of 500ing a user-facing route.

        The rate limiter (utils/rate_limit.py) is the one sanctioned exception: it
        must pass the stability kwargs to the `limits` library's own storage
        constructor (it can't use our helpers), and it already imports the shared
        retry policy from redis_state.
        """
        import pathlib
        import re

        app_dir = pathlib.Path(redis_state.__file__).parent.parent  # app/
        pat = re.compile(r"\b(redis|aioredis|redis_lib)\.(from_url|Redis)\s*\(")
        offenders = []
        for sub in ("routes", "services"):
            for py in (app_dir / sub).glob("*.py"):
                for i, line in enumerate(py.read_text().splitlines(), 1):
                    if line.lstrip().startswith("#"):
                        continue
                    if pat.search(line):
                        offenders.append(f"{sub}/{py.name}:{i}: {line.strip()}")
        assert not offenders, (
            "raw Redis client(s) in routes/ or services/ (use get_redis_client() / "
            "get_async_redis_client(), bounded + retry-wrapped):\n"
            + "\n".join(offenders)
        )


class _FakeQuotaRedis:
    def __init__(self, data):
        self.data = data

    def hgetall(self, _key):
        return self.data


class TestOddsApiQuotaState:
    """Guardrails for quota state fallback and malformed cached values."""

    def test_quota_guard_fails_open_when_redis_unavailable(self, monkeypatch):
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: None)

        assert redis_state.check_quota_guard("poll_futures") == (True, "no_redis")

    def test_quota_guard_fails_open_on_malformed_remaining_value(self, monkeypatch):
        monkeypatch.setattr(
            redis_state,
            "get_redis_client",
            lambda: _FakeQuotaRedis({b"remaining": b"not-an-int"}),
        )

        assert redis_state.check_quota_guard("discover_events") == (True, "redis_error")

    def test_get_odds_api_quota_reports_error_for_malformed_cached_numbers(self, monkeypatch):
        monkeypatch.setattr(
            redis_state,
            "get_redis_client",
            lambda: _FakeQuotaRedis({b"remaining": b"250000", b"used": b"not-an-int"}),
        )

        assert get_odds_api_quota() == {"status": "error"}


class TestQuotaGuardDateIndependence:
    """Regression: the quota guard must never silently disable on a date rollover.

    A hardcoded QUOTA_GUARD_EXPIRY date once disabled the guard the moment the
    clock rolled past it (it expired 2026-04-01 and stopped protecting the
    quota). The guard is now purely `remaining`-driven and auto-recovers when
    the billing cycle refills `remaining`. These tests lock that in: no expiry
    constant may exist, the verdict logic must contain no date-based disable,
    and the verdict must depend only on `remaining`.
    """

    def _guard_with_remaining(self, monkeypatch, remaining):
        monkeypatch.setattr(
            redis_state,
            "get_redis_client",
            lambda: _FakeQuotaRedis({b"remaining": str(remaining).encode()}),
        )
        return redis_state.check_quota_guard

    def test_no_expiry_constant_exists(self):
        # The date-expiry constant that silently disabled the guard must never
        # be reintroduced in any form.
        assert not hasattr(redis_state, "QUOTA_GUARD_EXPIRY")
        assert not hasattr(redis_state, "QUOTA_GUARD_BILLING_DAY")

    def test_guard_source_has_no_date_based_disable(self):
        # The verdict logic must gate on `remaining` only — no expiry symbol and
        # no calendar comparison that could turn the guard off as time passes.
        src = inspect.getsource(redis_state.check_quota_guard)
        assert "QUOTA_GUARD_EXPIRY" not in src
        assert ".day" not in src  # no day-of-month based enable/disable

    def test_guard_trips_on_low_quota_independent_of_when_called(self, monkeypatch):
        # Below FULL_STOP: non-essential tasks are blocked regardless of date.
        guard = self._guard_with_remaining(monkeypatch, 10_000)
        assert guard("discover_events") == (False, "full_stop_10000")
        assert guard("poll_futures") == (False, "full_stop_10000")

    def test_guard_trips_at_absolute_stop(self, monkeypatch):
        guard = self._guard_with_remaining(monkeypatch, 100)
        assert guard("poll_odds", sport_key="baseball_mlb") == (
            False,
            "absolute_stop_100",
        )

    def test_guard_normal_at_current_summer_headroom(self, monkeypatch):
        # Live summer headroom (~4.78M/5M): guard stays in Normal mode — re-enabling
        # the (always-active) guard must not change behavior at high quota.
        guard = self._guard_with_remaining(monkeypatch, 4_779_372)
        assert guard("discover_events") == (True, "ok_4779372")
        assert guard("poll_futures") == (True, "ok_4779372")
        assert guard("poll_odds", sport_key="baseball_mlb") == (True, "ok_4779372")

    def test_verdict_depends_only_on_remaining(self, monkeypatch):
        # Same `remaining` → same verdict on every call (no time-varying state).
        guard = self._guard_with_remaining(monkeypatch, 35_000)
        first = guard("poll_odds", sport_key="baseball_mlb")
        second = guard("poll_odds", sport_key="baseball_mlb")
        assert first == second == (True, "live_only_35000")


class TestWorkerBootLiveness:
    """#1280 Item 3: worker-generation liveness primitives that let the
    phase-heartbeat watchdog tell a live wedge from a deploy-orphaned marker."""

    class _FakeRedis:
        def __init__(self, initial=None):
            self.store = dict(initial or {})

        def get(self, key):
            v = self.store.get(key)
            return v.encode() if isinstance(v, str) else v

        def setex(self, key, _ttl, value):
            self.store[key] = value

    def test_boot_id_stable_and_hex(self):
        a = redis_state.get_worker_boot_id()
        b = redis_state.get_worker_boot_id()
        assert a == b  # one id per process
        assert a and all(c in "0123456789abcdef" for c in a)

    def test_touch_then_alive_true(self):
        rc = self._FakeRedis()
        redis_state.touch_worker_liveness(rc)
        assert redis_state.worker_boot_alive(
            rc, redis_state.get_worker_boot_id()
        ) is True

    def test_alive_false_for_unknown_or_empty(self):
        rc = self._FakeRedis()
        assert redis_state.worker_boot_alive(rc, "never-registered") is False
        assert redis_state.worker_boot_alive(rc, "") is False
        assert redis_state.worker_boot_alive(rc, None) is False

    def test_touch_never_raises_on_broken_client(self):
        class _Boom:
            def setex(self, *a, **k):
                raise RuntimeError("redis down")

        # Must be swallowed — a liveness refresh can never break a task.
        redis_state.touch_worker_liveness(_Boom())


class TestVerdictAwareRecording:
    """Queue 300H (#1515): a run that returned without completing its work must
    not increment the completion-success counter, and must not read healthy."""

    def _client(self, monkeypatch, hashes=None, counters=None):
        fake = _FakeMetricsRedis(hashes if hashes is not None else {}, counters)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
        return fake

    def test_incomplete_does_not_touch_the_success_counter(self, monkeypatch):
        fake = self._client(monkeypatch)
        redis_state.record_task_incomplete(
            "compute_time_horizon_calibration", 1200.0,
            verdict="partial", verdict_reason="units:horizons_done=0/4",
        )
        assert f"{TASK_METRICS_PREFIX}:compute_time_horizon_calibration:successes" \
            not in fake.counters
        assert fake.counters[
            f"{TASK_METRICS_PREFIX}:compute_time_horizon_calibration:incompletes"
        ] == b"1"

    def test_incomplete_preserves_consecutive_failures(self, monkeypatch):
        # Partial progress is neither an escalation nor a reset. It must not
        # clear a real failure streak, and must not add to it.
        fake = self._client(
            monkeypatch, hashes={"coverage_metrics": {b"consecutive_failures": b"3"}}
        )
        redis_state.record_task_incomplete(
            "coverage_metrics", 500.0, verdict="partial", verdict_reason="terminal:partial",
        )
        assert fake.hashes["coverage_metrics"][b"consecutive_failures"] == b"3"

    def test_incomplete_stamps_the_verdict_and_reason(self, monkeypatch):
        fake = self._client(monkeypatch)
        redis_state.record_task_incomplete(
            "calibration_prices", 540000.0,
            verdict="partial", verdict_reason="terminal:partial",
        )
        hash_ = fake.hashes["calibration_prices"]
        assert hash_[b"last_verdict"] == b"partial"
        assert hash_[b"last_verdict_reason"] == b"terminal:partial"

    def test_success_stamps_complete(self, monkeypatch):
        fake = self._client(monkeypatch)
        redis_state.record_task_success(
            "coverage_metrics", 100.0, {"published": True},
            verdict="complete", verdict_reason="terminal:complete",
        )
        assert fake.hashes["coverage_metrics"][b"last_verdict"] == b"complete"
        assert fake.counters[f"{TASK_METRICS_PREFIX}:coverage_metrics:successes"] == b"1"

    def test_returned_failure_increments_consecutive(self, monkeypatch):
        fake = self._client(monkeypatch)
        redis_state.record_task_failure(
            "coverage_metrics", 100.0, "task returned a failed terminal",
            verdict="failed", verdict_reason="terminal:failed",
        )
        assert fake.hashes["coverage_metrics"][b"consecutive_failures"] == b"1"
        assert fake.hashes["coverage_metrics"][b"last_verdict"] == b"failed"

    def test_thrown_failure_keeps_its_own_verdict_label(self, monkeypatch):
        fake = self._client(monkeypatch)
        redis_state.record_task_failure("poll_odds", 100.0, "boom")
        assert fake.hashes["poll_odds"][b"last_verdict"] == b"thrown"

    def test_recording_never_raises_on_a_broken_client(self, monkeypatch):
        class _Boom:
            def pipeline(self):
                raise RuntimeError("redis down")

            def hget(self, *a, **k):
                raise RuntimeError("redis down")

        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _Boom())
        redis_state.record_task_incomplete("x", 1.0, verdict="partial", verdict_reason="r")
        redis_state.record_task_success("x", 1.0, {})
        redis_state.record_task_failure("x", 1.0, "e")


class TestWindowCounterDoesNotSlide:
    """r346 read `successes_24h: 1015` on an HOURLY task and called it frozen.
    It was never a 24h window: EXPIRE on every increment pushed the TTL out
    forever, so the counter accumulated for as long as the task kept
    succeeding. SET NX EX stamps the window once (gotcha #49, task form)."""

    def test_first_increment_stamps_a_24h_window(self, monkeypatch):
        fake = _FakeMetricsRedis({})
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
        redis_state.record_task_success("poll_odds", 1.0, {})
        sets = [c for c in fake.calls if c[0] == "set"]
        assert sets == [(
            "set", f"{TASK_METRICS_PREFIX}:poll_odds:successes", 0, 86400, True,
        )]

    def test_later_increments_never_re_expire_the_counter(self, monkeypatch):
        fake = _FakeMetricsRedis({})
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
        for _ in range(4):
            redis_state.record_task_success("poll_odds", 1.0, {})
        counter_key = f"{TASK_METRICS_PREFIX}:poll_odds:successes"
        # The metrics HASH is still refreshed every run (48h TTL, by design);
        # the 24h counter's expiry is stamped once and never slid.
        assert [c for c in fake.calls if c[0] == "expire" and c[1] == counter_key] == []
        assert fake.counters[counter_key] == b"4"


class TestIncompleteHealthIsNotGreen:
    """The false GREEN, at the read side."""

    def _metrics(self, monkeypatch, hash_, counters):
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis({"t": hash_}, counters=counters),
        )
        return redis_state.get_task_metrics("t")

    def test_partial_last_run_is_degraded_not_healthy(self, monkeypatch):
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"0", b"last_verdict": b"partial",
             b"last_verdict_reason": b"units:horizons_done=0/4"},
            {f"{TASK_METRICS_PREFIX}:t:incompletes": b"4"},
        )
        assert result["health"] == "degraded"
        assert result["incompletes_24h"] == 4
        assert result["last_verdict_reason"] == "units:horizons_done=0/4"

    def test_authoritative_unknown_is_degraded(self, monkeypatch):
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"0", b"last_verdict": b"unknown"},
            {f"{TASK_METRICS_PREFIX}:t:incompletes": b"1"},
        )
        assert result["health"] == "degraded"

    def test_returned_failure_is_degraded_immediately(self, monkeypatch):
        # One RETURNED failed terminal is the task's own verdict on itself.
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"1", b"last_verdict": b"failed"},
            {f"{TASK_METRICS_PREFIX}:t:failures": b"1"},
        )
        assert result["health"] == "degraded"

    def test_one_thrown_failure_keeps_the_existing_bands(self, monkeypatch):
        # Unchanged policy: a single transient exception does not degrade a
        # task. Changing that across ~100 tasks is not Queue 300H's business.
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"1", b"last_verdict": b"thrown"},
            {f"{TASK_METRICS_PREFIX}:t:failures": b"1",
             f"{TASK_METRICS_PREFIX}:t:successes": b"20"},
        )
        assert result["health"] == "healthy"

    def test_legacy_unverified_run_still_reads_healthy(self, monkeypatch):
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"0", b"last_verdict": b"unverified"},
            {f"{TASK_METRICS_PREFIX}:t:successes": b"12"},
        )
        assert result["health"] == "healthy"

    def test_a_later_complete_run_clears_the_degradation(self, monkeypatch):
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"0", b"last_verdict": b"complete"},
            {f"{TASK_METRICS_PREFIX}:t:successes": b"1",
             f"{TASK_METRICS_PREFIX}:t:incompletes": b"6"},
        )
        assert result["health"] == "healthy"

    def test_incompletes_alone_are_not_idle(self, monkeypatch):
        # A task recording ONLY incompletes has run — it must not fall into the
        # idle-first `no_data` branch and disappear from the health rollups.
        result = self._metrics(
            monkeypatch,
            {b"consecutive_failures": b"0", b"last_verdict": b"partial"},
            {f"{TASK_METRICS_PREFIX}:t:incompletes": b"3"},
        )
        assert result["health"] == "degraded"

    def test_truly_idle_task_still_reads_no_data(self, monkeypatch):
        result = self._metrics(
            monkeypatch, {b"consecutive_failures": b"9", b"last_verdict": b"partial"}, {},
        )
        assert result["health"] == "no_data"

    def test_partial_verdict_surfaces_in_the_degraded_rollup(self, monkeypatch):
        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda: _FakeMetricsRedis(
                {"compute_time_horizon_calibration": {
                    b"consecutive_failures": b"0", b"last_verdict": b"partial"}},
                counters={
                    f"{TASK_METRICS_PREFIX}:compute_time_horizon_calibration:incompletes": b"4"
                },
            ),
        )
        tasks = redis_state.get_all_task_metrics()
        degraded = [t["task"] for t in tasks if t.get("health") == "degraded"]
        assert degraded == ["compute_time_horizon_calibration"]
