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
from datetime import datetime, timedelta, timezone
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
    build_game_alert_payload,
    dispatch_game_alerts,
    is_close_late,
    is_final_period,
    is_just_started,
    parse_soccer_clock,
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
from app.utils.activitykit_payload import OBSERVATION_MAX_AGE
from app.utils.activitykit_projection import project_activitykit_snapshot
from app.utils.activitykit_start_payload import build_activitykit_start_alert

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
    commence_time: datetime | None = None,
    prob_observed_at: datetime | None = NOW,
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
    if commence_time is not None:
        detail["commence_time"] = commence_time.isoformat()
    if home_prob is not None and away_prob is not None:
        detail["hero_probability"] = home_prob
        detail["hero_probability_away"] = away_prob
        detail["hero_probability_source"] = "blended"
        if prob_observed_at is not None:
            detail["hero_probability_observed_at"] = prob_observed_at.isoformat()
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
        assert is_close_late(detail, now=NOW) is expected

    def test_non_live_or_early_period_is_not_close_late(self):
        assert is_close_late(_event_detail(status="scheduled", period="4th Quarter"), now=NOW) is False
        assert is_close_late(_event_detail(status="live", period="2nd Quarter"), now=NOW) is False
        assert is_close_late(_event_detail(status="completed", period="Final"), now=NOW) is False


# --- 2b. Fable look items 1-4: just-started, OBSERVATION_MAX_AGE, wording ----


class TestFableLookGuards:
    @pytest.mark.parametrize(
        ("period", "commence_offset_min", "expected"),
        [
            ("1st Quarter", -5, True),
            ("Q1", -25, True),
            ("1st Period", -10, True),
            ("1st Half", -8, True),
            ("Top 1st", -12, True),
            ("1st Set", -10, True),
            # Mid-game / later periods must NEVER send "Starting now"
            ("2nd Quarter", -35, False),
            ("3rd Quarter", -90, False),
            ("4th Quarter", -120, False),
            ("Halftime", -60, False),
            ("End of 1st Quarter", -20, False),
            ("2nd Half", -50, False),
            ("OT", -160, False),
            # Missing period label falls back to <= 15 minutes from commence_time
            (None, -5, True),
            (None, -15, True),
            (None, -16, False),
            (None, -90, False),
        ],
    )
    def test_start_alert_only_fires_when_game_just_went_live(
        self, period, commence_offset_min, expected
    ):
        detail = _event_detail(
            event_id=701,
            status="live",
            period=period,
            commence_time=NOW + timedelta(minutes=commence_offset_min),
        )
        assert is_just_started(detail, now=NOW) is expected
        push = build_game_alert_payload(
            detail, trigger_kind="start", device_id=uuid4(), now=NOW
        )
        assert (push is not None) is expected

    def test_stale_probability_blocks_close_late_and_drops_number_on_start(self):
        stale_ts = NOW - OBSERVATION_MAX_AGE - timedelta(seconds=1)
        fresh_ts = NOW - OBSERVATION_MAX_AGE + timedelta(seconds=1)

        stale_late = _event_detail(
            event_id=702, period="4th Quarter", home_prob=0.52, away_prob=0.48, prob_observed_at=stale_ts
        )
        fresh_late = _event_detail(
            event_id=702, period="4th Quarter", home_prob=0.52, away_prob=0.48, prob_observed_at=fresh_ts
        )
        assert is_close_late(stale_late, now=NOW) is False
        assert (
            build_game_alert_payload(
                stale_late, trigger_kind="close_late", device_id=uuid4(), now=NOW
            )
            is None
        )
        assert is_close_late(fresh_late, now=NOW) is True

        stale_start = _event_detail(
            event_id=703, period="1st Quarter", home_prob=0.52, away_prob=0.48, prob_observed_at=stale_ts
        )
        fresh_start = _event_detail(
            event_id=703, period="1st Quarter", home_prob=0.52, away_prob=0.48, prob_observed_at=fresh_ts
        )
        push_stale = build_game_alert_payload(
            stale_start, trigger_kind="start", device_id=uuid4(), now=NOW
        )
        push_fresh = build_game_alert_payload(
            fresh_start, trigger_kind="start", device_id=uuid4(), now=NOW
        )
        assert push_stale is not None and push_stale.body == "Starting now"
        assert push_fresh is not None and push_fresh.body == "Starting now · Lakers 52%"

    def test_start_wording_matches_activitykit_start_alert_builder(self):
        detail = _event_detail(event_id=704, period="1st Quarter", home_prob=0.52, away_prob=0.48)
        expected = build_activitykit_start_alert(
            project_activitykit_snapshot(detail), sent_at=NOW
        )
        push = build_game_alert_payload(
            detail, trigger_kind="start", device_id=uuid4(), now=NOW
        )
        assert push is not None
        assert push.title == expected["title"]
        assert push.body == expected["body"]

    def test_final_wording_uses_won_for_both_players_and_teams(self):
        tennis_final = _event_detail(
            event_id=705,
            sport="tennis_atp_us_open",
            status="completed",
            away_team="Alcaraz",
            home_team="Sinner",
            home_score=3,
            away_score=1,
            period="Final",
            home_prob=None,
            away_prob=None,
            result="home",
        )
        push = build_game_alert_payload(
            tennis_final, trigger_kind="final", device_id=uuid4(), now=NOW
        )
        assert push is not None
        assert push.body == "Sinner won"
        assert "win" not in push.body.lower()


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

        start_detail = _event_detail(
            event_id=500,
            sport="basketball_nba",
            status="live",
            period="1st Quarter",
            home_prob=0.55,
            away_prob=0.45,
            home_score=4,
            away_score=2,
            commence_time=NOW - timedelta(minutes=5),
        )
        live_late_detail = _event_detail(
            event_id=501,
            sport="basketball_nba",
            status="live",
            period="4th Quarter",
            home_prob=0.53,
            away_prob=0.47,
            home_score=101,
            away_score=99,
            commence_time=NOW - timedelta(hours=2),
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

        details = {500: start_detail, 501: live_late_detail, 502: final_detail}

        async def _reader(db, eid):
            return details[eid]

        pool = _RecordingPool()
        dedup = _MemoryDedup()
        summary = await dispatch_game_alerts(
            _dummy_sessions(),
            pool,
            lambda: _const(VALID_JWT),
            dedup,
            now=NOW,
            detail_reader=_reader,
            live_finder=lambda db, ts: _const([500, 501]),
            final_finder=lambda db, ts: _const([502]),
        )

        # Event 500 (1st Quarter):
        #   - start -> dev_plain ONLY (dev_with_la is in plan.start, not plan.alert)
        #   - close_late -> none (not final period)
        # Event 501 (4th Quarter, close_late):
        #   - start -> none (already Q4, not just started)
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

        # Production got: dev_plain start (500), dev_plain close_late (501), dev_plain final (502), dev_clip final (502)
        prod_pairs = [(tok, p.trigger_kind, p.event_id, topic) for tok, p, topic, _ in prod_sent]
        assert (HEX_TOKEN_A, "start", 500, alert_topic("ios")) in prod_pairs
        assert (HEX_TOKEN_A, "start", 501, alert_topic("ios")) not in prod_pairs
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
            live_finder=lambda db, ts: _const([500, 501]),
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


def _soccer_detail(
    *,
    clock: str | None = "78'",
    period: str | None = "2nd Half",
    home_prob: float | None = 0.28,
    away_prob: float | None = 0.20,
    draw_prob: float | None = 0.52,
    prob_age: timedelta = timedelta(seconds=30),
) -> dict:
    obs_iso = (NOW - prob_age).isoformat()
    espn: dict[str, object] = {}
    if period is not None:
        espn["period"] = period
    if clock is not None:
        espn["game_clock"] = clock
    odds: dict[str, object] = {}
    if home_prob is not None:
        odds["home_probability"] = home_prob
    if away_prob is not None:
        odds["away_probability"] = away_prob
    if draw_prob is not None:
        odds["draw_probability"] = draw_prob
    return {
        "id": 9876,
        "sport": "soccer_epl",
        "status": "live",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_score": 1,
        "away_score": 1,
        "espn": espn,
        "current_odds": odds,
        "hero_probability": home_prob,
        "hero_probability_away": away_prob,
        "hero_probability_draw": draw_prob,
        "hero_probability_observed_at": obs_iso,
        "hero_probability_source": "blend",
    }


class TestSoccerCloseLate271A:
    @pytest.mark.parametrize(
        "raw_clock,period,expected",
        [
            ("75'", "2nd Half", (75, "75'")),
            ("78'", "2nd Half", (78, "78'")),
            ("90'+2'", "2nd Half", (90, "90+2'")),
            ("90+3'", "2nd Half", (90, "90+3'")),
            ("82:15", "2nd Half", (82, "82'")),
            ("105'", "Extra Time", (105, "105'")),
            ("74'", "2nd Half", (74, "74'")),
            ("45'+3'", "1st Half", None),
            ("78'", "1st Half", None),
            ("78'", "Halftime", None),
            ("90'", "FT", None),
            ("HT", "2nd Half", None),
            ("FT", "2nd Half", None),
            (None, "2nd Half", None),
            ("", "2nd Half", None),
        ],
    )
    def test_parse_soccer_clock(self, raw_clock, period, expected):
        assert parse_soccer_clock(raw_clock, period=period) == expected

    def test_soccer_75th_minute_threshold_and_missing_clock_refusal(self):
        # 74' -> too early
        assert is_close_late(_soccer_detail(clock="74'"), now=NOW) is False
        # 75' -> inclusive threshold -> buzzes
        assert is_close_late(_soccer_detail(clock="75'"), now=NOW) is True
        # 90'+2' stoppage -> buzzes
        assert is_close_late(_soccer_detail(clock="90'+2'"), now=NOW) is True
        # No game clock on the feed -> no buzz even in 2nd Half
        assert is_close_late(_soccer_detail(clock=None, period="2nd Half"), now=NOW) is False
        assert is_close_late(_soccer_detail(clock="", period="2nd Half"), now=NOW) is False

    def test_soccer_three_way_max_65_percent_rule(self):
        # Draw 52%, home 28%, away 20% -> max 52% <= 65% -> buzzes
        assert is_close_late(
            _soccer_detail(home_prob=0.28, away_prob=0.20, draw_prob=0.52), now=NOW
        ) is True
        # Draw 65% -> boundary inclusive -> buzzes
        assert is_close_late(
            _soccer_detail(home_prob=0.20, away_prob=0.15, draw_prob=0.65), now=NOW
        ) is True
        # Draw 66% -> > 65% -> no buzz
        assert is_close_late(
            _soccer_detail(home_prob=0.20, away_prob=0.14, draw_prob=0.66), now=NOW
        ) is False
        # Home 66% -> > 65% -> no buzz
        assert is_close_late(
            _soccer_detail(home_prob=0.66, away_prob=0.10, draw_prob=0.24), now=NOW
        ) is False
        # Away 66% -> > 65% -> no buzz
        assert is_close_late(
            _soccer_detail(home_prob=0.10, away_prob=0.66, draw_prob=0.24), now=NOW
        ) is False
        # Missing draw probability -> never guesses 2-way -> no buzz
        assert is_close_late(
            _soccer_detail(home_prob=0.50, away_prob=0.50, draw_prob=None), now=NOW
        ) is False
        # Stale observation (> 6 min) -> no buzz
        assert is_close_late(
            _soccer_detail(prob_age=OBSERVATION_MAX_AGE + timedelta(seconds=1)),
            now=NOW,
        ) is False

    def test_soccer_draw_in_play_wording_never_prints_lower_side_as_leader(self):
        # Draw is likeliest (52%) -> prints "Close late (78') — draw 52%"
        push_draw = build_game_alert_payload(
            _soccer_detail(clock="78'", home_prob=0.28, away_prob=0.20, draw_prob=0.52),
            trigger_kind="close_late",
            device_id=uuid4(),
            now=NOW,
        )
        assert push_draw is not None
        assert push_draw.title == "Chelsea 1–1 Arsenal"
        assert push_draw.body == "Close late (78') — draw 52%"

        # Home leads (54%) -> prints "Close late (78') — Arsenal 54%"
        push_home = build_game_alert_payload(
            _soccer_detail(clock="78'", home_prob=0.54, away_prob=0.18, draw_prob=0.28),
            trigger_kind="close_late",
            device_id=uuid4(),
            now=NOW,
        )
        assert push_home is not None
        assert push_home.body == "Close late (78') — Arsenal 54%"

        # Away leads (58%) in stoppage time -> prints "Close late (90+2') — Chelsea 58%"
        push_away = build_game_alert_payload(
            _soccer_detail(clock="90'+2'", home_prob=0.18, away_prob=0.58, draw_prob=0.24),
            trigger_kind="close_late",
            device_id=uuid4(),
            now=NOW,
        )
        assert push_away is not None
        assert push_away.body == "Close late (90+2') — Chelsea 58%"

    def test_mens_college_basketball_2nd_half_unchanged_without_clock(self):
        # Ruling 271: A — men's college half is 20 minutes (same as a hockey period),
        # so it stays as built from 259: A.
        obs_iso = (NOW - timedelta(seconds=30)).isoformat()
        ncaab = {
            "id": 5555,
            "sport": "basketball_ncaab",
            "status": "live",
            "home_team": "Duke",
            "away_team": "UNC",
            "home_score": 68,
            "away_score": 66,
            "espn": {"period": "2nd Half"},
            "current_odds": {"home_probability": 0.56, "away_probability": 0.44},
            "hero_probability": 0.56,
            "hero_probability_away": 0.44,
            "hero_probability_observed_at": obs_iso,
            "hero_probability_source": "blend",
        }
        assert is_close_late(ncaab, now=NOW) is True
        push = build_game_alert_payload(
            ncaab, trigger_kind="close_late", device_id=uuid4(), now=NOW
        )
        assert push is not None
        assert push.body == "Close late (2nd Half) · Duke 56%"


async def _const(value):
    return value
