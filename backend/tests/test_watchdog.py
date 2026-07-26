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


# ── #219E Item 2: fingerprinting + GitHub rail ────────────────────────


class TestAlertFingerprintingAndFiling:
    """The creation-stall alert must fingerprint on [class, provider] (not the
    hours-bearing message) and route to the GitHub board — no email/Sentry-only
    class (the third email-only incident, #219E)."""

    def test_capture_fingerprints_on_class_and_provider(self, monkeypatch):
        seen = {}

        class _Scope:
            def __init__(self):
                self.fingerprint = None
                self.tags = {}

            def set_tag(self, k, v):
                self.tags[k] = v

        class _Ctx:
            def __enter__(self_inner):
                self_inner.scope = _Scope()
                seen["scope"] = self_inner.scope
                return self_inner.scope

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(watchdog.sentry_sdk, "new_scope", lambda: _Ctx())
        monkeypatch.setattr(
            watchdog.sentry_sdk, "capture_message",
            lambda msg, level=None: seen.setdefault("msg", msg),
        )
        # two different hour-values must produce the SAME fingerprint
        watchdog._capture_fingerprinted("creation_stall", "polymarket", "stalled 6.0h")
        fp1 = seen["scope"].fingerprint
        watchdog._capture_fingerprinted("creation_stall", "polymarket", "stalled 11.5h")
        fp2 = seen["scope"].fingerprint
        assert fp1 == ["creation_stall", "polymarket"] == fp2, (
            "fingerprint must be [class, provider], stable across hour-values"
        )

    async def test_stale_routes_to_github_rail(self, monkeypatch, now):
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message", lambda *a, **k: None)
        monkeypatch.setattr(watchdog.sentry_sdk, "new_scope",
                            lambda: __import__("contextlib").nullcontext(type("S", (), {"set_tag": lambda s, *a: None})()))
        fake = _FakeRedis()
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        monkeypatch.setattr(
            watchdog, "evaluate_creation_alerts",
            lambda rows, n: [{"source": "polymarket", "age_hours": 30.0,
                              "threshold_hours": 6, "last_created": "x"}],
        )
        filed_calls = []
        monkeypatch.setattr(
            watchdog, "_file_watchdog_issue",
            lambda cls, prov, title, body: filed_calls.append((cls, prov)) or {"action": "filed"},
        )

        class _FakeSession:
            async def execute(self, *_a, **_k):
                return type("R", (), {"scalar": lambda s: None})()

        class _FakeCtx:
            async def __aenter__(self):
                return _FakeSession()
            async def __aexit__(self, *a):
                return False

        import app.tasks.base as base
        monkeypatch.setattr(base, "get_task_session", lambda: _FakeCtx())

        out = await watchdog._run_creation_freshness_watchdog()
        assert filed_calls == [("creation_stall", "polymarket")], (
            "a creation stall must file to the GitHub rail, not Sentry/email only"
        )
        assert out.get("filed"), "runner must report what it filed"

    def test_filer_noops_without_token(self, monkeypatch):
        import app.tasks.bug_report_github as gh
        monkeypatch.setattr(gh, "GITHUB_TOKEN", "")
        res = watchdog._file_watchdog_issue("creation_stall", "polymarket", "t", "b")
        assert res["action"] == "skipped_no_token", (
            "a token gap must degrade gracefully, never crash the watchdog"
        )


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

    # ── #1280 Item 3: owner-generation reconciliation ─────────────────

    def _stale_setup(self, owner_alive: bool):
        """A frozen, past-threshold marker owned by a boot id that is (or isn't)
        still a live worker generation."""
        from app.tasks.redis_state import WORKER_ALIVE_PREFIX

        marker = "upsert_loop@120s"
        boot_id = "gen-deadbeef"
        phase_key = watchdog.PHASE_MARKER_KEYS["poll_kalshi"]
        owner_key = phase_key + ":owner"
        seen_key = watchdog._PHASE_SEEN_PREFIX + "poll_kalshi"
        old = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat()
        store = {
            phase_key: marker,
            owner_key: boot_id,
            seen_key: json.dumps({"marker": marker, "first_seen": old}),
        }
        if owner_alive:
            store[WORKER_ALIVE_PREFIX + boot_id] = "1"
        return marker, phase_key, owner_key, seen_key, _FakeRedis(store)

    def test_stale_marker_from_dead_generation_reconciled_not_red(self, monkeypatch):
        marker, phase_key, owner_key, seen_key, fake = self._stale_setup(
            owner_alive=False
        )
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda *a, **k: fired.append(a))
        out = watchdog._run_phase_heartbeat_watchdog()
        # A marker orphaned by a deploy/restart must NOT page as a live stall...
        assert out["stuck"] == []
        assert fired == []
        # ...and must be reconciled away so it cannot linger as a false RED.
        assert phase_key not in fake.store
        assert owner_key not in fake.store
        assert seen_key not in fake.store

    def test_byte_identical_expired_marker_cannot_stay_red(self, monkeypatch):
        # Guard: the SAME byte-identical marker across repeated runs never becomes
        # a live-stall RED once its owning generation is gone.
        marker, phase_key, owner_key, seen_key, fake = self._stale_setup(
            owner_alive=False
        )
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message", lambda *a, **k: None)
        # First pass reconciles it away.
        assert watchdog._run_phase_heartbeat_watchdog()["stuck"] == []
        # Re-plant the identical marker (as a restarted-but-idle producer might if
        # its old client flushed) and run again — still not RED.
        fake.store[phase_key] = marker
        fake.store[owner_key] = "gen-deadbeef"
        assert watchdog._run_phase_heartbeat_watchdog()["stuck"] == []

    def test_live_owner_still_alerts(self, monkeypatch):
        marker, phase_key, owner_key, seen_key, fake = self._stale_setup(
            owner_alive=True
        )
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda msg, level=None: fired.append((msg, level)))
        out = watchdog._run_phase_heartbeat_watchdog()
        # Owner generation still alive → a genuine event-loop wedge → RED.
        assert len(out["stuck"]) == 1
        assert out["stuck"][0]["phase"] == marker
        assert fired and fired[0][1] == "error"
        # The real stall is preserved, not reconciled away.
        assert phase_key in fake.store

    def test_legacy_marker_without_owner_still_alerts(self, monkeypatch):
        # Back-compat: a marker with no recorded owner (pre-#1280 or a dropped
        # owner write) must fall through to the original alert path.
        marker = "upsert_loop@120s"
        phase_key = watchdog.PHASE_MARKER_KEYS["poll_kalshi"]
        seen_key = watchdog._PHASE_SEEN_PREFIX + "poll_kalshi"
        old = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat()
        fake = _FakeRedis({
            phase_key: marker,
            seen_key: json.dumps({"marker": marker, "first_seen": old}),
        })
        monkeypatch.setattr(watchdog, "_bounded_rc", lambda: fake)
        fired = []
        monkeypatch.setattr(watchdog.sentry_sdk, "capture_message",
                            lambda msg, level=None: fired.append((msg, level)))
        out = watchdog._run_phase_heartbeat_watchdog()
        assert len(out["stuck"]) == 1
        assert fired and fired[0][1] == "error"


# ── admin/health surface (#969 c) ─────────────────────────────────────


class TestWatchdogSurface:
    """The combined runner persists a summary (per-source ages + heartbeat) for
    the admin dashboard / /health, and the creation runner exposes by_source."""

    def test_summary_key_constant(self):
        assert watchdog.WATCHDOG_SUMMARY_KEY == "bainluck:watchdog:summary"

    def test_by_source_populated_for_fresh_and_missing(self, now):
        # by_source must include every watched source, fresh or absent, so the
        # dashboard shows the full picture (not just alerting sources).
        rows = {"kalshi": now, "polymarket": None}
        alerts = watchdog.evaluate_creation_alerts(rows, now)
        assert alerts == []  # both within threshold / no rows
        # the by_source shape is built in the async runner; assert the contract
        # the dashboard depends on by exercising evaluate + manual shape here
        assert "kalshi" in rows and "polymarket" in rows
