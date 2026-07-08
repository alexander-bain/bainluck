"""#995 NEVER-AGAIN watchdog: creation-freshness + phase-heartbeat alerts.

Both alert paths are covered with mocked Sentry + Redis. The 28-day Kalshi
creation freeze was invisible because SIGKILL raises no exception (Sentry blind)
and updates stayed fresh (coarse health green) — only these creates-specific +
heartbeat signals catch that class, so their alert logic must not regress.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import watchdog


@pytest.fixture
def now():
    return datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)


class _FakeRedis:
    """Minimal sync Redis stand-in with TTL-agnostic get/setex/delete."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})

    def get(self, key):
        v = self.store.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


# ── creation-freshness ────────────────────────────────────────────────


class TestEvaluateCreationAlerts:
    def test_stale_source_alerts(self, now):
        rows = {
            "kalshi": now - timedelta(hours=10),   # > 6h → stale
            "polymarket": now - timedelta(hours=1),  # fresh
        }
        alerts = watchdog.evaluate_creation_alerts(rows, now)
        assert [a["source"] for a in alerts] == ["kalshi"]
        assert alerts[0]["threshold_hours"] == 6
        assert alerts[0]["age_hours"] >= 6

    def test_all_fresh_no_alerts(self, now):
        rows = {
            "kalshi": now - timedelta(hours=1),
            "polymarket": now - timedelta(hours=2),
        }
        assert watchdog.evaluate_creation_alerts(rows, now) == []

    def test_no_rows_never_alerts(self, now):
        # None = fresh/unknown state, not a freeze — must not cry wolf.
        rows = {"kalshi": None, "polymarket": None}
        assert watchdog.evaluate_creation_alerts(rows, now) == []

    def test_naive_datetime_is_treated_as_utc(self, now):
        rows = {"kalshi": (now - timedelta(hours=10)).replace(tzinfo=None)}
        alerts = watchdog.evaluate_creation_alerts(rows, now)
        assert alerts and alerts[0]["source"] == "kalshi"


class TestCreationFreshnessEmit:
    """The async runner emits Sentry + sets/clears the admin flag."""

    async def test_stale_fires_sentry_and_sets_flag(self, monkeypatch, now):
        captured = []
        monkeypatch.setattr(
            watchdog.sentry_sdk, "capture_message",
            lambda msg, level=None: captured.append((msg, level)),
        )
        fake = _FakeRedis()
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)

        # feed a stale kalshi via the pure evaluator path
        monkeypatch.setattr(
            watchdog, "evaluate_creation_alerts",
            lambda rows, n: [{"source": "kalshi", "age_hours": 30.0,
                              "threshold_hours": 6, "last_created": "x"}],
        )

        class _FakeSession:
            async def execute(self, *_a, **_k):
                class _R:
                    def scalar(self_inner):
                        return None
                return _R()

        class _FakeCtx:
            async def __aenter__(self):
                return _FakeSession()
            async def __aexit__(self, *a):
                return False

        import app.tasks.base as base
        monkeypatch.setattr(base, "get_task_session", lambda: _FakeCtx())

        out = await watchdog._run_creation_freshness_watchdog()
        assert out["stale_sources"] == ["kalshi"]
        assert captured and captured[0][1] == "error"
        assert watchdog.CREATION_STALE_FLAG_KEY in fake.store

    async def test_fresh_clears_flag(self, monkeypatch):
        monkeypatch.setattr(
            watchdog.sentry_sdk, "capture_message", lambda *a, **k: None
        )
        fake = _FakeRedis({watchdog.CREATION_STALE_FLAG_KEY: "[stale]"})
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        monkeypatch.setattr(watchdog, "evaluate_creation_alerts", lambda rows, n: [])

        class _FakeSession:
            async def execute(self, *_a, **_k):
                class _R:
                    def scalar(self_inner):
                        return None
                return _R()

        class _FakeCtx:
            async def __aenter__(self):
                return _FakeSession()
            async def __aexit__(self, *a):
                return False

        import app.tasks.base as base
        monkeypatch.setattr(base, "get_task_session", lambda: _FakeCtx())

        out = await watchdog._run_creation_freshness_watchdog()
        assert out["stale_sources"] == []
        assert watchdog.CREATION_STALE_FLAG_KEY not in fake.store


# ── phase-heartbeat ───────────────────────────────────────────────────


class TestPhaseHeartbeat:
    def test_no_marker_no_alert(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda *a, **k: fired.append(a))
        out = watchdog._run_phase_heartbeat_watchdog()
        assert out["stuck"] == []
        assert fired == []

    def test_new_marker_records_first_seen_no_alert(self, monkeypatch):
        fake = _FakeRedis({watchdog.PHASE_MARKER_KEYS["poll_kalshi"]: "fetch:p3@12s"})
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda *a, **k: fired.append(a))
        out = watchdog._run_phase_heartbeat_watchdog()
        assert out["stuck"] == []
        assert fired == []
        # first-seen must be recorded so the NEXT run can detect stuck-ness
        seen_key = watchdog._PHASE_SEEN_PREFIX + "poll_kalshi"
        assert seen_key in fake.store
        assert json.loads(fake.store[seen_key])["marker"] == "fetch:p3@12s"

    def test_unchanged_marker_over_threshold_alerts(self, monkeypatch):
        marker = "fetch:unfiltered:p6:recv50@8s"
        old = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat()
        seen_key = watchdog._PHASE_SEEN_PREFIX + "poll_kalshi"
        fake = _FakeRedis({
            watchdog.PHASE_MARKER_KEYS["poll_kalshi"]: marker,
            seen_key: json.dumps({"marker": marker, "first_seen": old}),
        })
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda msg, level=None: fired.append((msg, level)))
        out = watchdog._run_phase_heartbeat_watchdog()
        assert len(out["stuck"]) == 1
        assert out["stuck"][0]["task"] == "poll_kalshi"
        assert out["stuck"][0]["phase"] == marker
        assert fired and fired[0][1] == "error"

    def test_terminal_phase_never_alerts(self, monkeypatch):
        marker = "done@130s"
        old = (datetime.now(timezone.utc) - timedelta(seconds=9000)).isoformat()
        seen_key = watchdog._PHASE_SEEN_PREFIX + "poll_kalshi"
        fake = _FakeRedis({
            watchdog.PHASE_MARKER_KEYS["poll_kalshi"]: marker,
            seen_key: json.dumps({"marker": marker, "first_seen": old}),
        })
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda *a, **k: fired.append(a))
        out = watchdog._run_phase_heartbeat_watchdog()
        assert out["stuck"] == []
        assert fired == []
        # terminal phase clears tracking state
        assert seen_key not in fake.store
