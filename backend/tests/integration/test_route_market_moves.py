"""Contract tests for market moves endpoint.

Tests:
- GET /api/market-moves — 'The Market Was Wrong' surprises feed

Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock


def _mock_scalars_all(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _mock_unique_scalars_all(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.unique.return_value.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _sport(key="basketball_nba", name="NBA"):
    return SimpleNamespace(key=key, name=name)


def _event(
    event_id,
    *,
    home_prob,
    away_prob=None,
    home_score=3,
    away_score=1,
    home_team="Home",
    away_team="Away",
    sport=None,
):
    return SimpleNamespace(
        id=event_id,
        sport=sport or _sport(),
        opening_home_probability=home_prob,
        opening_away_probability=away_prob,
        home_score=home_score,
        away_score=away_score,
        home_team_name=home_team,
        away_team_name=away_team,
        commence_time=datetime.now(timezone.utc) - timedelta(hours=2),
    )


def _market(
    market_id,
    *,
    outcomes,
    market_tier=1,
    sport=None,
    name="NBA Championship",
    llm_sport_category="basketball",
):
    return SimpleNamespace(
        id=market_id,
        name=name,
        market_tier=market_tier,
        sport=sport or _sport(),
        llm_sport_category=llm_sport_category,
        outcomes=outcomes,
    )


def _outcome(name, *, current_probability, probability_change_24h):
    return SimpleNamespace(
        name=name,
        current_probability=current_probability,
        probability_change_24h=probability_change_24h,
    )


class TestMarketMovesEndpoint:
    """GET /api/market-moves — recent market surprises."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/market-moves")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/market-moves")
        body = resp.json()
        assert isinstance(body, dict)
        assert set(body) == {"items", "total", "hours", "generated_at"}
        assert body["items"] == []
        assert body["total"] == 0
        assert body["hours"] == 48
        datetime.fromisoformat(body["generated_at"])

    async def test_hours_param_accepted(self, client):
        resp = await client.get("/api/market-moves?hours=72")
        assert resp.status_code == 200

    async def test_limit_param_accepted(self, client):
        resp = await client.get("/api/market-moves?limit=5")
        assert resp.status_code == 200

    async def test_hours_too_low_returns_422(self, client):
        resp = await client.get("/api/market-moves?hours=1")
        assert resp.status_code == 422

    async def test_hours_too_high_returns_422(self, client):
        resp = await client.get("/api/market-moves?hours=999")
        assert resp.status_code == 422

    async def test_limit_too_high_returns_422(self, client):
        resp = await client.get("/api/market-moves?limit=100")
        assert resp.status_code == 422

    async def test_limit_zero_returns_422(self, client):
        resp = await client.get("/api/market-moves?limit=0")
        assert resp.status_code == 422

    async def test_hours_boundary_params_accepted(self, client):
        low = await client.get("/api/market-moves?hours=6")
        high = await client.get("/api/market-moves?hours=168")

        assert low.status_code == 200
        assert low.json()["hours"] == 6
        assert high.status_code == 200
        assert high.json()["hours"] == 168

    async def test_limit_boundary_param_accepted(self, client):
        resp = await client.get("/api/market-moves?limit=50")
        assert resp.status_code == 200

    async def test_non_integer_params_return_422(self, client):
        hours_resp = await client.get("/api/market-moves?hours=soon")
        limit_resp = await client.get("/api/market-moves?limit=many")

        assert hours_resp.status_code == 422
        assert limit_resp.status_code == 422

    async def test_empty_mocked_data_returns_empty_contract(self, client, mock_db):
        mock_db.execute.side_effect = [
            _mock_scalars_all([]),
            _mock_unique_scalars_all([]),
        ]

        resp = await client.get("/api/market-moves?hours=24&limit=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["hours"] == 24
        assert mock_db.execute.call_count == 2

    async def test_sorts_by_score_desc_and_applies_limit(self, client, mock_db):
        upset = _event(
            1,
            home_prob=0.2,
            away_prob=0.8,
            home_score=4,
            away_score=2,
            home_team="Falcons",
            away_team="Wolves",
        )
        market_error = _event(
            2,
            home_prob=0.7,
            away_prob=0.3,
            home_score=5,
            away_score=3,
            home_team="Sharks",
            away_team="Bears",
        )
        futures_mover = _market(
            10,
            outcomes=[
                _outcome(
                    "Falcons",
                    current_probability=0.42,
                    probability_change_24h=0.4,
                )
            ],
        )
        mock_db.execute.side_effect = [
            _mock_scalars_all([market_error, upset]),
            _mock_unique_scalars_all([futures_mover]),
        ]

        resp = await client.get("/api/market-moves?limit=2")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert [item["type"] for item in body["items"]] == ["upset", "futures_mover"]
        assert body["items"][0]["score"] >= body["items"][1]["score"]
        assert body["items"][0]["winner"] == "Falcons"
        assert body["items"][1]["outcome_name"] == "Falcons"

    async def test_filters_low_signal_events_and_futures(self, client, mock_db):
        tie = _event(
            1,
            home_prob=0.8,
            away_prob=0.2,
            home_score=2,
            away_score=2,
        )
        small_error = _event(
            2,
            home_prob=0.93,
            away_prob=0.07,
            home_score=1,
            away_score=0,
        )
        weak_upset = _event(
            3,
            home_prob=0.46,
            away_prob=0.54,
            home_score=3,
            away_score=2,
        )
        valid_upset = _event(
            4,
            home_prob=0.3,
            away_prob=0.7,
            home_score=6,
            away_score=1,
            home_team="Tigers",
            away_team="Kings",
        )
        futures = _market(
            20,
            outcomes=[
                _outcome(
                    "Tiny Move",
                    current_probability=0.35,
                    probability_change_24h=0.02,
                ),
                _outcome(
                    "No Price",
                    current_probability=None,
                    probability_change_24h=0.09,
                ),
            ],
        )
        mock_db.execute.side_effect = [
            _mock_scalars_all([tie, small_error, weak_upset, valid_upset]),
            _mock_unique_scalars_all([futures]),
        ]

        resp = await client.get("/api/market-moves")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["type"] == "upset"
        assert body["items"][0]["event_id"] == 4
