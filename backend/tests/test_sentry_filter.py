"""#1501 — Sentry `before_send` volume filter.

The org's error quota (5,000/month, resets the 21st) has been exhausted since
2026-07-29: 0 accepted, 3,999 rate-limited, 29,800 client-discarded over 14 days
= ~2,414 offered/day against a ~164/day budget. The consequence is not lost
noise, it is that **a green Sentry read means nothing** — #1445 and #1199 both
failed silently behind a 0-events bucket that only meant the quota was gone.

These tests pin the three tiers and, most importantly, the properties that keep
the filter honest when it is wrong about the census:

* a NOVEL signature always sends its first event immediately;
* the filter fails OPEN — a bug in it must never suppress error reporting;
* dropping is narrow (Redis transport, not every ConnectionError).

The clock is injected, never read (gotcha #44): `_SignatureThrottle.allow` takes
`now`, so no assertion here depends on the wall clock.
"""

import pytest

from app.utils.sentry_filter import (
    BACKSTOP_PER_WINDOW,
    BACKSTOP_WINDOW_S,
    DROP_EXC_NAMES,
    THROTTLE_EXC_NAMES,
    THROTTLE_PER_WINDOW,
    THROTTLE_WINDOW_S,
    SentryVolumeFilter,
    _SignatureThrottle,
    _is_event_loop_noise,
    _is_redis_transport_error,
    build_before_send,
    event_signature,
)

# Real messages, copied from the production census (2026-07-21 -> 07-29).
REDIS_MSG = (
    "Error 8 connecting to ec2-3-92-219-100.compute-1.amazonaws.com:10819. "
    "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1006)."
)
REDIS_MSG_104 = "Error 104 connecting to ec2-3-92-219-100.compute-1.amazonaws.com:10819. Connection reset by peer."


def _event(transaction="app.tasks.poll_odds", exc_type="ValueError", value="boom"):
    return {
        "transaction": transaction,
        "exception": {"values": [{"type": exc_type, "value": value}]},
    }


def _hint(exc_type_name, message="boom"):
    exc_cls = type(exc_type_name, (Exception,), {})
    return {"exc_info": (exc_cls, exc_cls(message), None)}


class TestRedisTransportDetection:
    """Drop the Heroku Redis TLS churn — but ONLY that."""

    @pytest.mark.parametrize("exc", ["ConnectionError", "TimeoutError", "OperationalError"])
    def test_heroku_redis_tls_reset_is_transport_noise(self, exc):
        assert _is_redis_transport_error(exc, REDIS_MSG) is True

    def test_connection_reset_variant(self):
        assert _is_redis_transport_error("ConnectionError", REDIS_MSG_104) is True

    def test_upstream_http_connection_error_is_NOT_dropped(self):
        """The class we must never lose: a real upstream API outage."""
        msg = "HTTPSConnectionPool(host='api.the-odds-api.com', port=443): Max retries exceeded"
        assert _is_redis_transport_error("ConnectionError", msg) is False

    def test_unrelated_exception_name_is_not_transport(self):
        assert _is_redis_transport_error("ValueError", REDIS_MSG) is False

    def test_redis_word_alone_is_not_enough(self):
        """Needs BOTH a host marker and a transport marker, not just 'redis'."""
        assert _is_redis_transport_error("ConnectionError", "redis key missing") is False


class TestEventLoopNoise:
    def test_event_loop_closed_is_noise(self):
        assert _is_event_loop_noise("RuntimeError", "Event loop is closed") is True

    def test_different_loop_is_noise(self):
        assert _is_event_loop_noise("RuntimeError", "attached to a different loop") is True

    def test_other_runtime_errors_are_real(self):
        assert _is_event_loop_noise("RuntimeError", "something genuinely broke") is False

    def test_non_runtime_error_is_not_loop_noise(self):
        assert _is_event_loop_noise("ValueError", "Event loop is closed") is False


class TestSignature:
    def test_signature_uses_transaction_not_message(self):
        """Messages carry hostnames/PIDs/row-ids that would defeat dedup entirely
        — which is precisely how one class spends a month's quota."""
        a = event_signature(_event(value="host-A pid 1"), "ConnectionError")
        b = event_signature(_event(value="host-B pid 2"), "ConnectionError")
        assert a == b

    def test_same_exception_different_task_is_a_different_signature(self):
        a = event_signature(_event(transaction="app.tasks.poll_odds"), "SoftTimeLimitExceeded")
        b = event_signature(_event(transaction="app.tasks.backfill_winners"), "SoftTimeLimitExceeded")
        assert a != b

    def test_missing_transaction_does_not_crash(self):
        assert event_signature({}, "ValueError").startswith("ValueError|")


class TestThrottleBucket:
    """Clock is injected — nothing here reads the wall clock (gotcha #44)."""

    def test_first_event_always_allowed(self):
        t = _SignatureThrottle()
        assert t.allow("sig", limit=1, window_s=100, now=0.0) is True

    def test_limit_enforced_within_window(self):
        t = _SignatureThrottle()
        assert t.allow("sig", limit=2, window_s=100, now=0.0) is True
        assert t.allow("sig", limit=2, window_s=100, now=10.0) is True
        assert t.allow("sig", limit=2, window_s=100, now=20.0) is False

    def test_window_rolls_over(self):
        t = _SignatureThrottle()
        assert t.allow("sig", limit=1, window_s=100, now=0.0) is True
        assert t.allow("sig", limit=1, window_s=100, now=50.0) is False
        assert t.allow("sig", limit=1, window_s=100, now=100.0) is True

    def test_signatures_are_independent(self):
        t = _SignatureThrottle()
        assert t.allow("a", limit=1, window_s=100, now=0.0) is True
        assert t.allow("b", limit=1, window_s=100, now=0.0) is True

    def test_table_is_bounded(self):
        """This dict lives forever in a worker process — it must not grow."""
        t = _SignatureThrottle()
        for i in range(3000):
            t.allow(f"sig{i}", limit=1, window_s=100, now=float(i))
        assert len(t.snapshot()) <= 512


class TestFilterTiers:
    def test_redis_transport_error_is_dropped(self):
        f = SentryVolumeFilter()
        out = f(_event(exc_type="ConnectionError", value=REDIS_MSG), _hint("ConnectionError", REDIS_MSG))
        assert out is None
        assert f.counts["dropped"] == 1

    def test_pending_rollback_cascade_is_dropped(self):
        f = SentryVolumeFilter()
        assert f(_event(exc_type="PendingRollbackError"), _hint("PendingRollbackError")) is None
        assert f.counts["dropped"] == 1

    def test_upstream_connection_error_passes(self):
        f = SentryVolumeFilter()
        msg = "HTTPSConnectionPool(host='api.the-odds-api.com', port=443): Max retries exceeded"
        assert f(_event(exc_type="ConnectionError", value=msg), _hint("ConnectionError", msg)) is not None
        assert f.counts["passed"] == 1

    def test_celery_death_is_throttled_not_dropped(self):
        """First one gets through — the alarm survives; the repeats do not."""
        f = SentryVolumeFilter()
        ev = _event(exc_type="SoftTimeLimitExceeded", value="")
        assert f(ev, _hint("SoftTimeLimitExceeded", "")) is not None
        for _ in range(50):
            f(ev, _hint("SoftTimeLimitExceeded", ""))
        assert f.counts["passed"] == 1
        assert f.counts["throttled"] == 50
        assert f.counts["dropped"] == 0

    def test_workerlosterror_is_matched(self):
        """The web filter said 'WorkerLost'; billiard's class is 'WorkerLostError',
        so the largest Celery class never matched. Both names are covered now."""
        assert "WorkerLostError" in THROTTLE_EXC_NAMES
        assert "WorkerLost" in THROTTLE_EXC_NAMES
        f = SentryVolumeFilter()
        ev = _event(exc_type="WorkerLostError", value="")
        assert f(ev, _hint("WorkerLostError", "")) is not None
        assert f(ev, _hint("WorkerLostError", "")) is None

    def test_softtimelimit_is_covered_at_all(self):
        """It was absent from the original inline filter entirely."""
        assert "SoftTimeLimitExceeded" in THROTTLE_EXC_NAMES

    def test_plain_runtime_error_is_not_throttled_as_loop_noise(self):
        f = SentryVolumeFilter()
        ev = _event(exc_type="RuntimeError", value="a real bug")
        for _ in range(BACKSTOP_PER_WINDOW):
            assert f(ev, _hint("RuntimeError", "a real bug")) is not None
        assert f.counts["passed"] == BACKSTOP_PER_WINDOW

    def test_event_loop_noise_is_throttled(self):
        f = SentryVolumeFilter()
        ev = _event(exc_type="RuntimeError", value="Event loop is closed")
        assert f(ev, _hint("RuntimeError", "Event loop is closed")) is not None
        assert f(ev, _hint("RuntimeError", "Event loop is closed")) is None


class TestBackstop:
    """The part that does NOT depend on the census being right."""

    def test_novel_signature_always_sends_its_first_event(self):
        """The single property that separates this from blanket sampling."""
        f = SentryVolumeFilter()
        for i in range(200):
            ev = _event(transaction=f"app.tasks.task_{i}", exc_type="BrandNewError")
            assert f(ev, _hint("BrandNewError")) is not None, "a novel error was suppressed"

    def test_unidentified_flooding_signature_is_capped(self):
        """A class nobody has censused cannot consume the whole quota."""
        f = SentryVolumeFilter()
        ev = _event(exc_type="SomeUnknownFlood")
        sent = sum(1 for _ in range(5000) if f(ev, _hint("SomeUnknownFlood")) is not None)
        assert sent == BACKSTOP_PER_WINDOW
        assert f.counts["backstopped"] == 5000 - BACKSTOP_PER_WINDOW

    def test_distinct_signatures_each_get_their_own_allowance(self):
        f = SentryVolumeFilter()
        for i in range(5):
            ev = _event(transaction=f"t{i}", exc_type="Whatever")
            for _ in range(10):
                f(ev, _hint("Whatever"))
        assert f.counts["passed"] == 5 * BACKSTOP_PER_WINDOW


class TestFailOpen:
    """A filter bug must never take error reporting down with it."""

    def test_malformed_event_does_not_raise(self):
        f = SentryVolumeFilter()
        assert f({}, None) is not None
        assert f({"exception": None}, {}) is not None

    def test_internal_error_fails_open(self, monkeypatch):
        f = SentryVolumeFilter()
        monkeypatch.setattr(
            "app.utils.sentry_filter._exc_name_and_value",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("filter bug")),
        )
        ev = _event()
        assert f(ev, _hint("ValueError")) is ev, "filter must fail OPEN, not swallow"

    def test_hint_without_exc_info_uses_the_event_body(self):
        f = SentryVolumeFilter()
        ev = _event(exc_type="ConnectionError", value=REDIS_MSG)
        assert f(ev, {}) is None  # still recognised as redis transport noise


class TestWiring:
    def test_both_entry_points_use_the_shared_filter(self):
        """#1501's root cause: the filter existed but only on the web process."""
        import inspect

        import app.main as main_mod
        import app.tasks as tasks_mod

        for mod in (main_mod, tasks_mod):
            src = inspect.getsource(mod)
            assert "build_before_send" in src, f"{mod.__name__} not wired to the shared filter"
            assert "before_send=" in src, f"{mod.__name__} passes no before_send"

    def test_builder_returns_independent_instances(self):
        a, b = build_before_send(), build_before_send()
        assert a is not b

    def test_caps_are_tight_enough_to_fit_the_budget(self):
        """Projection guard: 5,000/month = 164/day. Loosening these without
        re-measuring is what re-exhausts the quota."""
        assert THROTTLE_PER_WINDOW <= 2
        assert BACKSTOP_PER_WINDOW <= 4
        assert THROTTLE_WINDOW_S >= 3600
        assert BACKSTOP_WINDOW_S >= 3600


class TestCensusReplay:
    """Replay the REAL 07-21 -> 07-29 census composition through the filter.

    Counts are the production signature census. The assertion is on the tier
    split, which is what the volume projection in #1501 rests on.
    """

    CENSUS = [
        ("ConnectionError", REDIS_MSG, 2011),
        ("SoftTimeLimitExceeded", "", 654),
        ("WorkerLostError", "", 246),
        ("TimeLimitExceeded", "", 153),
        ("RuntimeError", "Event loop is closed", 131),
        ("DBAPIError", "QueryCanceledError", 83),
        ("IntegrityError", "duplicate key value", 54),
        ("PendingRollbackError", "rolled back", 54),
        ("SchedulingError", "Couldn't apply scheduled task", 27),
        ("ProgrammingError", "relation does not exist", 17),
    ]

    def test_replay_cuts_the_dominant_share(self):
        f = SentryVolumeFilter()
        before = sent = 0
        for i, (exc, msg, n) in enumerate(self.CENSUS):
            ev = _event(transaction=f"app.tasks.t{i}", exc_type=exc, value=msg)
            for _ in range(n):
                before += 1
                if f(ev, _hint(exc, msg)) is not None:
                    sent += 1
        cut = 1 - sent / before
        # Single-signature-per-class replay is the filter's best case; the real
        # census spreads these over ~100 signatures. Both must clear the bar.
        assert cut > 0.95, f"only cut {cut:.1%}"
        assert f.counts["dropped"] >= 2011 + 54  # redis + rollback cascade

    def test_redis_class_contributes_nothing_after_filtering(self):
        f = SentryVolumeFilter()
        ev = _event(exc_type="ConnectionError", value=REDIS_MSG)
        for _ in range(2011):
            assert f(ev, _hint("ConnectionError", REDIS_MSG)) is None
        assert f.counts["passed"] == 0
