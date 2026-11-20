"""#13000 (Ruling 257: B): read-only Live Tennis API coverage probe tests."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

import pytest

from app.tasks import live_tennis_probe as probe

T0 = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex=None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def incr(self, key: str) -> int:
        val = int(self.store.get(key, "0")) + 1
        self.store[key] = str(val)
        return val

    def expire(self, key: str, ttl: int) -> bool:
        return True


@pytest.fixture(autouse=True)
def _reset_probe(monkeypatch):
    probe._reset_fallback_budget_for_tests()
    monkeypatch.delenv(probe.LIVE_TENNIS_API_KEY_ENV, raising=False)
    yield
    probe._reset_fallback_budget_for_tests()


class TestOffWhenKeyAbsent:
    @pytest.mark.asyncio
    async def test_disabled_makes_zero_db_or_http_calls(self, monkeypatch):
        called = {"db": 0, "http": 0}

        async def _boom_db():
            called["db"] += 1
            raise AssertionError("must not read DB when key is absent")

        async def _boom_http(_key: str):
            called["http"] += 1
            raise AssertionError("must not call HTTP when key is absent")

        monkeypatch.setattr(probe, "_load_live_tennis_events", _boom_db)
        monkeypatch.setattr(probe, "_fetch_live_tennis_payload", _boom_http)

        res = await probe.run_live_tennis_probe(now=T0)
        assert res["status"] == "disabled"
        assert res["reason"] == "LIVE_TENNIS_API_KEY_unset"
        assert called == {"db": 0, "http": 0}


class TestParsingMatchingAndBuckets:
    def test_extracts_singles_and_doubles_with_scores_and_matches_both_orientations(self):
        payload = {
            "data": [
                {
                    "id": 21131,
                    "tournament": "ATP Challenger Yokohama",
                    "tour": "challenger",
                    "status": "live",
                    "players": {
                        "p1": {"name": "Yi Zhou"},
                        "p2": {"name": "Yu Hsiou Hsu"},
                    },
                    "score": {"sets": [1, 0], "games": [[6, 4], [2, 1]], "points": ["30", "15"]},
                },
                {
                    "id": 21132,
                    "tournament": "ATP Challenger Yokohama Doubles",
                    "tour": "challenger",
                    "status": "live",
                    "players": {
                        "p1": {"name": "Cheng-Peng Hsieh / John-Patrick Smith"},
                        "p2": {"name": "Ray Ho / Pruchya Isaro"},
                    },
                    "score": {"sets": [0, 0], "games": [[4, 3]], "points": ["15", "0"]},
                },
                {
                    "id": 21133,
                    "tournament": "ITF M15 Sharm El Sheikh",
                    "tour": "itf",
                    "status": "live",
                    "players": {
                        "p1": {"name": "Tristan Boyer"},
                        "p2": {"name": "Genaro Olivieri"},
                    },
                    "score": {},
                },
            ]
        }
        feed = probe.extract_feed_matches(payload)
        assert len(feed) == 3
        assert feed[0]["has_score"] is True
        assert feed[1]["has_score"] is True
        assert feed[2]["has_score"] is False

        our_events = [
            {
                "id": 15350957,
                "home_team_name": "Hsu",
                "away_team_name": "Zhou",
                "external_id": "KXATPCHALLENGERMATCH-26NOV19HSUZHO",
                "home_score": None,
                "away_score": None,
                "period": None,
                "event_tags": [],
                "box_score_data": None,
                "sport_key": "tennis_atp",
            },
            {
                "id": 15350958,
                "home_team_name": "Hsieh C-P / Smith",
                "away_team_name": "Ho / Isaro",
                "external_id": "KXATPCHALLENGERMATCH-26NOV19HSISMI",
                "home_score": None,
                "away_score": None,
                "period": None,
                "event_tags": [],
                "box_score_data": None,
                "sport_key": "tennis_atp",
            },
            {
                "id": 15350959,
                "home_team_name": "Boyer",
                "away_team_name": "Olivieri",
                "external_id": "KXITFMATCH-26NOV19BOYOLI",
                "home_score": None,
                "away_score": None,
                "period": None,
                "event_tags": ["itf"],
                "box_score_data": None,
                "sport_key": "tennis_atp",
            },
            {
                "id": 15350960,
                "home_team_name": "Unlisted A / Unlisted B",
                "away_team_name": "Unlisted C / Unlisted D",
                "external_id": "KXITFMATCH-26NOV19UNL",
                "home_score": None,
                "away_score": None,
                "period": None,
                "event_tags": ["itf"],
                "box_score_data": None,
                "sport_key": "tennis_wta",
            },
        ]

        summary = probe.summarize_probe(our_events, feed)
        assert summary["totals"] == {
            "our_live": 4,
            "our_scoreless": 4,
            "feed_total": 3,
            "carried": 3,
            "carried_with_score": 2,
            "missing": 1,
        }
        assert summary["by_bucket"]["challenger_singles"]["carried_with_score"] == 1
        assert summary["by_bucket"]["challenger_doubles"]["carried_with_score"] == 1
        assert summary["by_bucket"]["itf_singles"]["carried"] == 1
        assert summary["by_bucket"]["itf_singles"]["carried_with_score"] == 0
        assert summary["by_bucket"]["itf_doubles"]["missing"] == 1


class TestBudgetAndKeySafety:
    @pytest.mark.asyncio
    async def test_skips_http_when_no_live_tennis_events(self, monkeypatch):
        monkeypatch.setenv(probe.LIVE_TENNIS_API_KEY_ENV, "sample-probe-value-alpha")
        http_calls = 0

        async def _empty_db():
            return []

        async def _http(_key: str):
            nonlocal http_calls
            http_calls += 1
            return {"data": []}

        monkeypatch.setattr(probe, "_load_live_tennis_events", _empty_db)
        monkeypatch.setattr(probe, "_fetch_live_tennis_payload", _http)

        res = await probe.run_live_tennis_probe(now=T0)
        assert res["status"] == "skipped"
        assert res["reason"] == "no_live_tennis_events"
        assert http_calls == 0

    @pytest.mark.asyncio
    async def test_enforces_daily_cap_and_min_interval_and_never_logs_key(
        self, monkeypatch, caplog
    ):
        sentinel_key = "sample-probe-value-beta"
        monkeypatch.setenv(probe.LIVE_TENNIS_API_KEY_ENV, sentinel_key)
        fake_redis = _FakeRedis()
        monkeypatch.setattr(probe, "_redis_client", lambda: fake_redis)

        live_row = [
            {
                "id": 15350957,
                "home_team_name": "Hsu",
                "away_team_name": "Zhou",
                "external_id": "KXATPCHALLENGERMATCH-1",
                "home_score": None,
                "away_score": None,
                "period": None,
                "event_tags": [],
                "box_score_data": None,
                "sport_key": "tennis_atp",
            }
        ]

        async def _db():
            return live_row

        calls = 0

        async def _http(api_key: str):
            nonlocal calls
            assert api_key == sentinel_key
            calls += 1
            return {"data": []}

        monkeypatch.setattr(probe, "_load_live_tennis_events", _db)
        monkeypatch.setattr(probe, "_fetch_live_tennis_payload", _http)

        with caplog.at_level(logging.INFO):
            first = await probe.run_live_tennis_probe(now=T0)
            assert first["status"] == "ok"
            assert first["daily_calls"] == 1
            assert calls == 1

            # Immediate retry inside 15-minute window is blocked by min_interval_guard.
            second = await probe.run_live_tennis_probe(now=T0)
            assert second["status"] == "skipped"
            assert second["reason"] == "min_interval_guard"
            assert calls == 1

            # Simulate daily cap reached (96/96) -> blocked even after interval clears.
            fake_redis.store.pop(probe.REDIS_LAST_FETCH_KEY, None)
            fake_redis.store[f"{probe.REDIS_DAILY_KEY_PREFIX}2026-06-15"] = str(
                probe.DAILY_REQUEST_CAP
            )
            third = await probe.run_live_tennis_probe(now=T0)
            assert third["status"] == "skipped"
            assert third["reason"] == "daily_cap_reached"
            assert calls == 1

        # Key must never appear in any logged message.
        for record in caplog.records:
            assert sentinel_key not in record.getMessage()
