"""Contract tests for GET /api/events/{id} with seeded mock data.

Tests the full event detail response shape, related futures structure,
and game-markets sections when the DB returns pre-built event rows.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db


def _make_event(
    id: int = 1,
    home_team: str = "Celtics",
    away_team: str = "76ers",
    status: str = "live",
    sport_key: str = "basketball_nba",
    home_prob: float = 0.65,
    home_score: int | None = 88,
    away_score: int | None = 82,
):
    event = MagicMock()
    event.id = id
    event.external_id = f"ext-{id}"
    event.home_team_name = home_team
    event.away_team_name = away_team
    event.status = status
    event.sport_key = sport_key
    event.sport_id = 1
    event.sport = MagicMock()
    event.sport.key = sport_key
    event.sport.name = "Basketball"
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    event.completed_at = None
    event.home_score = home_score
    event.away_score = away_score
    event.win_probability_sources = {"betting": {"home_probability": home_prob}}
    event.current_home_probability = home_prob
    event.current_away_probability = 1 - home_prob
    event.espn_game_id = None
    event.espn_id = None
    event.espn_data = None
    event.espn_win_prob_home = None
    event.game_clock = None
    event.period = None
    event.broadcast_info = None
    event.event_tags = []
    event.pulse_score = None
    event.pulse_label = None
    event.excite_index = None
    event.raw_ei = None
    event.home_team_id = None
    event.away_team_id = None
    event.llm_gender = None
    event.llm_level = None
    event.llm_league = None
    event.llm_importance = None
    return event


def _make_futures_market(
    id: int = 100,
    name: str = "NBA Championship Winner 2025-26",
    source: str = "kalshi",
    sport_category: str = "basketball",
    leader_name: str = "Celtics",
    leader_prob: float = 0.25,
):
    market = MagicMock()
    market.id = id
    market.name = name
    market.source = source
    market.status = "open"
    market.llm_sport_category = sport_category
    market.market_tier = 1
    market.category = "championship"
    market.event_id = None
    market.volume_24h = 5000.0
    market.resolution_date = datetime.now(timezone.utc) + timedelta(days=60)
    market.image_url = None
    market.hook_description = None
    market.external_id = f"{source}-{id}"
    market.canonical_market_key = None
    market.outcome_count = 10
    return market


def _make_outcome(
    id: int = 1,
    name: str = "Celtics",
    probability: float = 0.25,
    market_id: int = 100,
):
    outcome = MagicMock()
    outcome.id = id
    outcome.name = name
    outcome.probability = probability
    outcome.market_id = market_id
    outcome.opening_probability = probability - 0.05
    return outcome


def _make_event_detail_session(event=None, snapshots=None, futures=None, outcomes=None):
    """Create a mock DB session that routes queries to the right data."""
    session = AsyncMock()

    def make_scalar_result(data):
        result = MagicMock()
        result.scalar_one_or_none.return_value = data
        result.scalars.return_value.all.return_value = [data] if data else []
        result.scalars.return_value.first.return_value = data
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    def make_list_result(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data or []
        result.scalars.return_value.first.return_value = (data[0]) if data else None
        result.scalar_one_or_none.return_value = len(data) if data else 0
        result.scalar.return_value = len(data) if data else 0
        result.fetchall.return_value = data or []
        result.all.return_value = [(r,) for r in (data or [])]
        result.first.return_value = (data[0],) if data else None
        return result

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    empty_result.scalars.return_value.first.return_value = None
    empty_result.scalar_one_or_none.return_value = None
    empty_result.scalar.return_value = None
    empty_result.fetchall.return_value = []
    empty_result.all.return_value = []
    empty_result.first.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower() if hasattr(stmt, "__str__") else ""
        if "events" in stmt_str and event:
            return make_scalar_result(event)
        if "odds_snapshots" in stmt_str:
            return make_list_result(snapshots or [])
        if "futures_outcomes" in stmt_str:
            return make_list_result(outcomes or [])
        if "futures_markets" in stmt_str:
            return make_list_result(futures or [])
        if "teams" in stmt_str:
            return empty_result
        return empty_result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


@pytest.fixture
async def event_detail_client():
    """Client with a seeded live event for detail page tests."""
    from app.main import app

    event = _make_event(id=1, home_team="Celtics", away_team="76ers", status="live")
    mock_session = _make_event_detail_session(event=event)

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


class TestEventDetailShape:
    """Event detail should return the full response shape for a live event."""

    async def test_returns_200(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        assert resp.status_code == 200

    async def test_has_core_fields(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        for field in ["id", "home_team", "away_team", "status", "commence_time"]:
            assert field in body, f"Missing field: {field}"

    async def test_id_matches_request(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert body["id"] == 1

    async def test_teams_are_strings(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert isinstance(body["home_team"], str)
        assert isinstance(body["away_team"], str)
        assert body["home_team"] == "Celtics"
        assert body["away_team"] == "76ers"

    async def test_status_is_valid(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert body["status"] in {"live", "scheduled", "completed", "closed"}

    async def test_live_event_has_scores(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert body["home_score"] is not None
        assert body["away_score"] is not None

    async def test_commence_time_is_iso_string(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert isinstance(body["commence_time"], str)
        assert "T" in body["commence_time"]

    async def test_sport_field_present(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert "sport" in body
        assert body["sport"] == "basketball_nba"


class TestEventDetailCurrentOdds:
    """When bookmaker snapshots exist, current_odds should be present."""

    async def test_current_odds_structure(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        if "current_odds" in body:
            odds = body["current_odds"]
            assert "home_probability" in odds
            assert "away_probability" in odds
            if odds["home_probability"] is not None:
                assert 0 <= odds["home_probability"] <= 1
            if odds["away_probability"] is not None:
                assert 0 <= odds["away_probability"] <= 1


class TestEventDetailNotFound:
    """Non-existent events should return 404."""

    async def test_404_for_missing_event(self, client):
        resp = await client.get("/api/events/999999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"] == "Event not found"


class TestGameMarketsShape:
    """GET /api/events/{id}/game-markets should have structured sections."""

    async def test_returns_200_or_404(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/game-markets")
        assert resp.status_code in (200, 404)

    async def test_sections_present_on_200(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            for section in ["totals", "player_props", "spreads", "other"]:
                assert section in body, f"Missing section: {section}"
            assert isinstance(body["totals"], list)
            assert isinstance(body["player_props"], list)
            assert isinstance(body["spreads"], list)
            assert isinstance(body["other"], list)

    async def test_has_event_context(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            assert body.get("event_id") == 1


class TestRelatedFuturesShape:
    """GET /api/events/{id}/related-futures response shape."""

    async def test_returns_200_or_404(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/related-futures")
        assert resp.status_code in (200, 404)

    async def test_response_has_futures_list(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/related-futures")
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, dict)
            if "futures" in body:
                assert isinstance(body["futures"], list)


class TestEventHistoryShape:
    """GET /api/events/{id}/history should return chart-ready data."""

    async def test_returns_200_or_404(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/history")
        assert resp.status_code in (200, 404)

    async def test_response_is_dict(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/history")
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, dict)
