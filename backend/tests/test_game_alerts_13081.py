"""Unit & integration-style tests for 1.0.8 plain APNs game alerts (#13081, #13079).

Covers:
- Ruling 258: A — Starts alert goes ONLY to opted-in devices that cannot start
  a Live Activity (`kickoff_plan.alert`), never to Live Activity start targets
  and never to a phone already showing an active Live Activity for that game.
- Ruling 259: A — Close-late trigger fires ONLY in the final period (or OT/ET)
  when win probability is between 35% and 65% inclusive, across NBA, WNBA,
  NCAAB, WNCAA, NFL, NCAAF, NHL, MLB, Soccer, and Tennis.
- Ruling 260: A — Close-late suppresses phones already showing that game's Live
  Activity; Final still buzzes EVERY opted-in phone, including Live Activity
  phones and valid (< 8 h) App Clip rows.
- Ruling 261: A — Standard APNs alert (`apns-push-type: alert`), NO
  `interruption-level: time-sensitive`, `event_id` carried in userInfo.
- Once-per-phone-per-game dedup (atomic Redis NX+EX; transient retry releases;
  accepted/410/rejected do not release) and 410 `forget_token` cleanup.
- App Clip 8-hour ephemeral expiry purge (`run_purge_expired_appclip_devices`)
  and default-off `GAME_ALERTS_PUSH_ENABLED` guard.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import httpx
import pytest

from app.services.activitykit_apns import APNsResult
from app.services.apns_alert import (
    APNsAlertTransport,
    GameAlertPush,
)
from app.services.game_alerts_dispatch import (
    dispatch_game_alerts,
    is_close_late,
    is_final_period,
)
from app.services.push_audience import (
    AlertTarget,
    KickoffPlan,
    StartTarget,
    alert_topic,
)
from app.tasks.game_alerts import (
    run_game_alerts_dispatch,
    run_purge_expired_appclip_devices,
)

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)
VALID_JWT = ".".join(["headerpart", "payloadpart", "sigpart123"])
HEX_TOKEN_A = "aa" * 32
HEX_TOKEN_B = "bb" * 32
HEX_TOKEN_CLIP = "cc" * 32


def _event_detail(
    *,
    event_id: int = 501,
    sport: str = "basketball_nba",
    status: str = "live",
    away_team: str = "Celtics",
    home_team: str = "Lakers",
    home_prob: float | None = 0.52,
    away_prob: float | None = 0.48,
    period: str | None = "4th Quarter",
    home_score: int | None = 98,
    away_score: int | None = 96,
    result: str | None = None,
) -> dict:
    detail: dict = {
        "id": event_id,
        "sport": sport,
        "status": status,
        "away_team": away_team,
        "home_team": home_team,
        "home_score": home_score,
        "away_score": away_score,
        "score_source": "espn" if home_score is not None else None,
        "score_observed_at": NOW.isoformat() if home_score is not None else None,
        "espn": {"period": period} if period is not None else {},
    }
    if home_prob is not None and away_prob is not None:
        detail["hero_probability"] = home_prob
        detail["hero_probability_away"] = away_prob
        detail["hero_probability_source"] = "blended"
        detail["hero_probability_observed_at"] = NOW.isoformat()
        detail["current_odds"] = {
            "home_probability": home_prob,
            "away_probability": away_prob,
        }
    if result is not None:
        detail["hero_settled_result"] = result
    return detail


class _MemoryDedup:
    def __init__(self) -> None:
        self.claimed: set[tuple[str, int, UUID]] = set()
        self.released: list[tuple[str, int, UUID]] = []

    async def claim(self, trigger_kind, event_id, device_id, ttl_seconds) -> bool:
        key = (trigger_kind, event_id, device_id)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    async def release(self, trigger_kind, event_id, device_id) -> None:
        key = (trigger_kind, event_id, device_id)
        self.claimed.discard(key)
        self.released.append(key)


class _RecordingTransport:
    def __init__(self, outcome_by_token: dict[str, APNsResult] | None = None) -> None:
        self.sent: list[tuple[str, GameAlertPush, str, str]] = []
        self._outcomes = outcome_by_token or {}

    async def send(
        self,
        push: GameAlertPush,
        *,
        device_token: str,
        topic: str,
        provider_token: str,
    ) -> APNsResult:
        self.sent.append((device_token, push, topic, provider_token))
        return self._outcomes.get(device_token, APNsResult("accepted", "apns_accepted"))


class _RecordingPool:
    def __init__(self, outcome_by_token: dict[str, APNsResult] | None = None) -> None:
        self.by_env: dict[str, _RecordingTransport] = {}
        self._outcomes = outcome_by_token or {}

    def for_env(self, apns_env: str) -> _RecordingTransport:
        env = "sandbox" if apns_env == "sandbox" else "production"
        if env not in self.by_env:
            self.by_env[env] = _RecordingTransport(self._outcomes)
        return self.by_env[env]

    async def aclose(self) -> None:
        return None


class _DummySession:
    def __init__(self) -> None:
        self.committed = 0

    async def commit(self) -> None:
        self.committed += 1


def _dummy_sessions(session: _DummySession | None = None):
    sess = session or _DummySession()

    @asynccontextmanager
    async def _ctx():
        yield sess

    return _ctx


# --- 1. APNs alert payload & HTTP/2 transport contract (Ruling 261: A) -------


class TestAPNsAlertTransport:
    def test_payload_uses_standard_interruption_level_and_event_id(self):
        push = GameAlertPush(
            event_id=777,
            trigger_kind="close_late",
            title="Celtics 98–96 Lakers",
            body="Close late (4th Quarter) — Lakers 52%",
            command_id="close_late:777:dev1",
            expiration_epoch=1736980000,
        )
        data = json.loads(push.to_apns_body().decode("utf-8"))
        assert data["event_id"] == 777
        assert data["trigger_kind"] == "close_late"
        assert data["aps"]["alert"]["title"] == "Celtics 98–96 Lakers"
        assert data["aps"]["sound"] == "default"
        # Ruling 261: A — never Time Sensitive
        assert "interruption-level" not in data["aps"]

    @pytest.mark.asyncio
    async def test_http2_headers_and_status_classification(self):
        captured: list[httpx.Request] = []
        statuses = [200, 410, 429, 400]

        class _MockH2(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                captured.append(request)
                code = statuses.pop(0)
                hdrs = {"retry-after": "12"} if code == 429 else {}
                return httpx.Response(
                    code,
                    headers=hdrs,
                    stream=httpx.ByteStream(b""),
                    extensions={"http_version": b"HTTP/2"},
                )

        transport = APNsAlertTransport(
            environment="production",
            transport=_MockH2(),
        )
        push = GameAlertPush(
            event_id=123,
            trigger_kind="final",
            title="Final: Lakers 104–101 Celtics",
            body="Lakers win",
            command_id="final:123:d1",
            expiration_epoch=1736980000,
        )
        try:
            r200 = await transport.send(
                push,
                device_token=HEX_TOKEN_A,
                topic=alert_topic("ios"),
                provider_token=VALID_JWT,
            )
            r410 = await transport.send(
                push,
                device_token=HEX_TOKEN_CLIP,
                topic=alert_topic("appclip"),
                provider_token=VALID_JWT,
            )
            r429 = await transport.send(
                push,
                device_token=HEX_TOKEN_A,
                topic=alert_topic("ios"),
                provider_token=VALID_JWT,
            )
            r400 = await transport.send(
                push,
                device_token=HEX_TOKEN_A,
                topic=alert_topic("ios"),
                provider_token=VALID_JWT,
            )
        finally:
            await transport.aclose()

        assert r200 == APNsResult("accepted", "apns_accepted")
        assert r410 == APNsResult("unavailable", "token_unregistered")
        assert r429.outcome == "retry" and r429.retry_after_seconds == 12
        assert r400 == APNsResult("rejected", "apns_rejected")

        assert captured[0].headers["apns-push-type"] == "alert"
        assert captured[0].headers["apns-priority"] == "10"
        assert captured[0].headers["apns-topic"] == alert_topic("ios")
        assert captured[1].headers["apns-topic"] == alert_topic("appclip")


# --- 2. Final period + close-late rules (Ruling 259: A) ----------------------


class TestCloseLateRule259A:
    @pytest.mark.parametrize(
        ("sport", "period", "expected"),
        [
            ("basketball_nba", "4th Quarter", True),
            ("basketball_nba", "5:21 - 4th Quarter", True),
            ("basketball_nba", "Q4", True),
            ("basketball_nba", "OT", True),
            ("basketball_nba", "2OT", True),
            ("basketball_nba", "3rd Quarter", False),
            ("basketball_nba", "End of 3rd Quarter", False),
            ("basketball_nba", "Halftime", False),
            ("basketball_nba", "Final/OT", False),
            ("basketball_ncaab", "2nd Half", True),
            ("basketball_ncaab", "1st Half", False),
            ("basketball_wncaab", "4th Quarter", True),
            ("basketball_wncaab", "2nd Quarter", False),
            ("americanfootball_nfl", "4th Quarter", True),
            ("americanfootball_nfl", "3rd Quarter", False),
            ("icehockey_nhl", "3rd Period", True),
            ("icehockey_nhl", "OT", True),
            ("icehockey_nhl", "Shootout", True),
            ("icehockey_nhl", "2nd Period", False),
            ("baseball_mlb", "Top 9th", True),
            ("baseball_mlb", "Bottom 10th", True),
            ("baseball_mlb", "Bottom 8th", False),
            ("baseball_mlb", "End 8th", False),
            ("soccer_epl", "2nd Half", True),
            ("soccer_epl", "Extra Time", True),
            ("soccer_epl", "1st Half", False),
            ("tennis_atp_us_open", "Final Set", True),
            ("tennis_atp_us_open", "3rd Set", True),
            ("tennis_atp_us_open", "1st Set", False),
        ],
    )
    def test_is_final_period_across_sports(self, sport, period, expected):
        assert is_final_period(sport, period) is expected

    @pytest.mark.parametrize(
        ("home_prob", "away_prob", "expected"),
        [
            (0.34, 0.66, False),
            (0.35, 0.65, True),
            (0.50, 0.50, True),
            (0.65, 0.35, True),
            (0.66, 0.34, False),
        ],
    )
    def test_probability_bounds_35_to_65_inclusive(self, home_prob, away_prob, expected):
        detail = _event_detail(
            sport="basketball_nba",
            status="live",
            period="4th Quarter",
            home_prob=home_prob,
            away_prob=away_prob,
        )
        assert is_close_late(detail) is expected

    def test_non_live_or_early_period_is_not_close_late(self):
        assert is_close_late(_event_detail(status="scheduled", period="4th Quarter")) is False
        assert is_close_late(_event_detail(status="live", period="2nd Quarter")) is False
        assert is_close_late(_event_detail(status="completed", period="Final")) is False


# --- 3. Dispatcher triggers, 258/260 suppression, dedup, 410, App Clip -------


class TestGameAlertsDispatch:
    @pytest.mark.asyncio
    async def test_starts_258_and_close_late_260_suppression_and_final_inclusion(
        self, monkeypatch
    ):
        import app.services.game_alerts_dispatch as mod

        dev_plain = uuid4()
        dev_with_la = uuid4()
        dev_clip = uuid4()

        target_plain = AlertTarget(
            device_id=dev_plain,
            platform="ios",
            apns_env="production",
            topic=alert_topic("ios"),
            token=HEX_TOKEN_A,
        )
        target_with_la = AlertTarget(
            device_id=dev_with_la,
            platform="ios",
            apns_env="sandbox",
            topic=alert_topic("ios"),
            token=HEX_TOKEN_B,
        )
        target_clip = AlertTarget(
            device_id=dev_clip,
            platform="appclip",
            apns_env="production",
            topic=alert_topic("appclip"),
            token=HEX_TOKEN_CLIP,
        )
        # dev_with_la has an la_start_token (in plan.start) AND an active LA.
        # dev_plain has no la_start_token (in plan.alert).
        async def _fake_kickoff_plan(db, event_id, *, now, min_app_version, after):
            return KickoffPlan(
                start=[
                    StartTarget(
                        device_id=dev_with_la,
                        apns_env="sandbox",
                        input_push_token=True,
                        app_version="1.0.8",
                        token="dd" * 32,
                    )
                ],
                alert=[target_plain],
                next_after=None,
            )

        async def _fake_alert_targets(db, kind, target_id, *, now, after):
            return [target_plain, target_with_la, target_clip]

        async def _fake_active_la(db, event_id, device_ids, *, now):
            return {dev_with_la} if dev_with_la in device_ids else set()

        monkeypatch.setattr(mod, "kickoff_plan", _fake_kickoff_plan)
        monkeypatch.setattr(mod, "alert_targets", _fake_alert_targets)
        monkeypatch.setattr(mod, "_active_la_device_ids", _fake_active_la)

        live_detail = _event_detail(
            event_id=501,
            sport="basketball_nba",
            status="live",
            period="4th Quarter",
            home_prob=0.53,
            away_prob=0.47,
            home_score=101,
            away_score=99,
        )
        final_detail = _event_detail(
            event_id=502,
            sport="americanfootball_nfl",
            status="completed",
            away_team="Bills",
            home_team="Chiefs",
            home_score=27,
            away_score=24,
            period="Final",
            home_prob=None,
            away_prob=None,
            result="home",
        )

        async def _reader(db, eid):
            return live_detail if eid == 501 else final_detail

        pool = _RecordingPool()
        dedup = _MemoryDedup()
        summary = await dispatch_game_alerts(
            _dummy_sessions(),
            pool,
            lambda: _const(VALID_JWT),
            dedup,
            now=NOW,
            detail_reader=_reader,
            live_finder=lambda db, ts: _const([501]),
            final_finder=lambda db, ts: _const([502]),
        )

        # Event 501 (live + close_late):
        #   - start -> dev_plain ONLY (dev_with_la is in plan.start, not plan.alert)
        #   - close_late -> dev_plain ONLY (dev_with_la suppressed by 260: A; dev_clip skipped)
        # Event 502 (final):
        #   - final -> ALL 3 (dev_plain, dev_with_la per 260: A, dev_clip per #13079)
        assert summary.start_accepted == 1
        assert summary.close_late_accepted == 1
        assert summary.final_accepted == 3
        assert summary.accepted == 5
        assert summary.skipped_active_la == 1

        prod_sent = pool.by_env["production"].sent
        sandbox_sent = pool.by_env["sandbox"].sent

        # Production got: dev_plain start, dev_plain close_late, dev_plain final, dev_clip final
        prod_pairs = [(tok, p.trigger_kind, p.event_id, topic) for tok, p, topic, _ in prod_sent]
        assert (HEX_TOKEN_A, "start", 501, alert_topic("ios")) in prod_pairs
        assert (HEX_TOKEN_A, "close_late", 501, alert_topic("ios")) in prod_pairs
        assert (HEX_TOKEN_A, "final", 502, alert_topic("ios")) in prod_pairs
        assert (HEX_TOKEN_CLIP, "final", 502, alert_topic("appclip")) in prod_pairs
        # App Clip did NOT get close_late
        assert all(
            not (tok == HEX_TOKEN_CLIP and kind == "close_late")
            for tok, kind, _, _ in prod_pairs
        )

        # Sandbox got ONLY dev_with_la final (suppressed on close_late & start)
        assert len(sandbox_sent) == 1
        assert sandbox_sent[0][0] == HEX_TOKEN_B
        assert sandbox_sent[0][1].trigger_kind == "final"
        assert sandbox_sent[0][1].event_id == 502

        # Second identical sweep is 100% deduped (zero double-buzzes)
        summary2 = await dispatch_game_alerts(
            _dummy_sessions(),
            pool,
            lambda: _const(VALID_JWT),
            dedup,
            now=NOW,
            detail_reader=_reader,
            live_finder=lambda db, ts: _const([501]),
            final_finder=lambda db, ts: _const([502]),
        )
        assert summary2.attempted == 0
        assert summary2.skipped_dedup == 5

    @pytest.mark.asyncio
    async def test_410_forgets_token_and_retry_releases_dedup(self, monkeypatch):
        import app.services.game_alerts_dispatch as mod

        dev_410 = uuid4()
        dev_retry = uuid4()
        t_410 = AlertTarget(dev_410, "ios", "production", alert_topic("ios"), HEX_TOKEN_A)
        t_retry = AlertTarget(dev_retry, "ios", "production", alert_topic("ios"), HEX_TOKEN_B)

        forgotten: list[tuple[str, str]] = []

        async def _fake_forget(db, col, tok):
            forgotten.append((col, tok))
            return 1

        async def _fake_alert_targets(db, kind, target_id, *, now, after):
            return [t_410, t_retry]

        monkeypatch.setattr(mod, "alert_targets", _fake_alert_targets)
        monkeypatch.setattr(mod, "forget_token", _fake_forget)

        sess = _DummySession()
        pool = _RecordingPool(
            outcome_by_token={
                HEX_TOKEN_A: APNsResult("unavailable", "token_unregistered"),
                HEX_TOKEN_B: APNsResult("retry", "apns_transient", 5),
            }
        )
        dedup = _MemoryDedup()
        final_detail = _event_detail(
            event_id=600,
            status="completed",
            home_score=3,
            away_score=1,
            period="Final",
            home_prob=None,
            away_prob=None,
            result="home",
        )
        summary = await dispatch_game_alerts(
            _dummy_sessions(sess),
            pool,
            lambda: _const(VALID_JWT),
            dedup,
            now=NOW,
            detail_reader=lambda db, eid: _const(final_detail),
            live_finder=lambda db, ts: _const([]),
            final_finder=lambda db, ts: _const([600]),
        )
        assert summary.token_forgotten == 1
        assert summary.retryable == 1
        assert forgotten == [("notification_token", HEX_TOKEN_A)]
        assert sess.committed == 1
        # Retry released dedup; 410 did NOT release dedup.
        assert ("final", 600, dev_retry) in dedup.released
        assert ("final", 600, dev_410) not in dedup.released


# --- 4. Default-off task guard + App Clip purge wiring -----------------------


class TestTaskGuardsAndAppClipPurge:
    @pytest.mark.asyncio
    async def test_game_alerts_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("GAME_ALERTS_PUSH_ENABLED", raising=False)
        res = await run_game_alerts_dispatch()
        assert res == {"status": "disabled", "terminal": "skipped"}

    @pytest.mark.asyncio
    async def test_appclip_purge_task_commits_deleted_count(self, monkeypatch):
        import app.tasks.game_alerts as mod

        class _FakeEngine:
            def __init__(self):
                self.disposed = False

            async def dispose(self):
                self.disposed = True

        sess = _DummySession()
        engine = _FakeEngine()

        monkeypatch.setattr(mod, "_get_task_engine", lambda **kw: engine)
        monkeypatch.setattr(mod, "async_sessionmaker", lambda eng, **kw: _dummy_sessions(sess))
        monkeypatch.setattr(
            mod,
            "purge_expired_appclip_devices",
            lambda db, *, now: _const(3),
        )
        res = await run_purge_expired_appclip_devices(now=NOW)
        assert res == {"status": "ok", "terminal": "ok", "deleted": 3}
        assert sess.committed == 1
        assert engine.disposed is True

    def test_beat_schedule_entries_registered_on_realtime(self):
        from app.tasks import celery_app

        beat = celery_app.conf.beat_schedule
        assert beat["game-alerts-push"]["task"] == "app.tasks.deliver_game_alerts"
        assert beat["game-alerts-push"]["options"]["queue"] == "realtime"
        assert (
            beat["purge-expired-appclip-devices"]["task"]
            == "app.tasks.purge_expired_appclip_devices"
        )
        assert beat["purge-expired-appclip-devices"]["options"]["queue"] == "realtime"


async def _const(value):
    return value
