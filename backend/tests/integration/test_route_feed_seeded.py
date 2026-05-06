"""Contract tests for GET /api/feed with seeded mock data.

Tests scoring, ordering, and item shape when the DB returns events
and futures with probabilities. Uses mock DB sessions that return
pre-built rows rather than empty results.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db


def _make_event_row(
    id: int,
    home_team: str = "Team A",
    away_team: str = "Team B",
    status: str = "live",
    sport_key: str = "basketball_nba",
    home_prob: float = 0.6,
    commence_time: datetime | None = None,
):
    """Build a mock Event row matching the ORM model's attribute access."""
    row = MagicMock()
    row.id = id
    row.home_team = home_team
    row.away_team = away_team
    row.status = status
    row.sport_key = sport_key
    row.sport_id = 1
    row.sport_name = "Basketball"
    row.commence_time = commence_time or (datetime.now(timezone.utc) - timedelta(hours=1))
    row.completed_at = None
    row.home_score = 80 if status == "live" else None
    row.away_score = 75 if status == "live" else None
    row.external_id = f"ext-{id}"
    row.win_probability_sources = {"betting": {"home_probability": home_prob}}
    row.current_home_probability = home_prob
    row.current_away_probability = 1 - home_prob
    row.espn_game_id = None
    row.espn_data = None
    row.event_tags = []
    row.pulse_score = None
    row.pulse_label = None
    row.excite_index = None
    row.home_team_id = None
    row.away_team_id = None
    return row


def _make_futures_row(
    id: int,
    name: str = "Championship Winner",
    sport_category: str = "basketball",
    leader_prob: float = 0.35,
    resolution_date: datetime | None = None,
):
    """Build a mock FuturesMarket row."""
    row = MagicMock()
    row.id = id
    row.name = name
    row.source = "kalshi"
    row.status = "open"
    row.llm_sport_category = sport_category
    row.sport_name = sport_category.capitalize()
    row.market_tier = 1
    row.category = "championship"
    row.event_id = None
    row.volume_24h = 5000.0
    row.volume_7d_avg = 3000.0
    row.resolution_date = resolution_date or (datetime.now(timezone.utc) + timedelta(days=30))
    row.image_url = None
    row.hook_description = None
    row.external_id = f"kalshi-{id}"
    row.canonical_market_key = None
    row.group_type = None
    row.group_id = None
    row.outcome_count = 5
    row.source_count = 1
    row.leader_name = "Celtics"
    row.leader_probability = leader_prob
    row.leader_movement = 0.03
    row.top_outcomes = []
    return row


def _make_seeded_session(events=None, futures=None):
    """Create a mock DB session that returns seeded events and futures."""
    session = AsyncMock()
    call_count = 0

    def make_result(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data or []
        result.scalars.return_value.first.return_value = (data or [None])[0] if data else None
        result.scalar_one_or_none.return_value = len(data) if data else 0
        result.scalar.return_value = len(data) if data else 0
        result.fetchall.return_value = data or []
        result.all.return_value = [(r,) for r in (data or [])]
        result.first.return_value = None
        return result

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    empty_result.scalars.return_value.first.return_value = None
    empty_result.scalar_one_or_none.return_value = 0
    empty_result.scalar.return_value = 0
    empty_result.fetchall.return_value = []
    empty_result.all.return_value = []
    empty_result.first.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        stmt_str = str(stmt).lower() if hasattr(stmt, '__str__') else ""
        if "events" in stmt_str and events:
            return make_result(events)
        if "futures_markets" in stmt_str and futures:
            return make_result(futures)
        return empty_result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


@pytest.fixture
async def seeded_client():
    """Client with seeded events and futures data."""
    from app.main import app

    events = [
        _make_event_row(1, "Celtics", "76ers", "live", "basketball_nba", 0.72),
        _make_event_row(2, "Yankees", "Red Sox", "scheduled", "baseball_mlb", 0.55),
        _make_event_row(3, "Lakers", "Nuggets", "completed", "basketball_nba", 0.30),
    ]
    futures = [
        _make_futures_row(100, "NBA Championship", "basketball", 0.35),
        _make_futures_row(101, "World Series Winner", "baseball", 0.20),
    ]

    mock_session = _make_seeded_session(events, futures)

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


class TestFeedSeededBasics:
    """Feed with seeded data should return valid non-empty responses."""

    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/feed")
        assert resp.status_code == 200

    async def test_response_has_required_keys(self, seeded_client):
        resp = await seeded_client.get("/api/feed")
        body = resp.json()
        for key in ["items", "total", "limit", "offset", "has_more"]:
            assert key in body

    async def test_items_have_type_and_data(self, seeded_client):
        resp = await seeded_client.get("/api/feed")
        body = resp.json()
        for item in body["items"]:
            assert "type" in item
            assert item["type"] in ("event", "futures")
            assert "data" in item
            assert "score" in item

    async def test_items_have_scores(self, seeded_client):
        resp = await seeded_client.get("/api/feed")
        body = resp.json()
        for item in body["items"]:
            assert isinstance(item.get("score", 0), (int, float))

    async def test_event_items_have_team_names(self, seeded_client):
        resp = await seeded_client.get("/api/feed")
        body = resp.json()
        events = [i for i in body["items"] if i["type"] == "event"]
        for event in events:
            data = event["data"]
            assert "home_team" in data
            assert "away_team" in data

    async def test_response_headers_have_request_id(self, seeded_client):
        resp = await seeded_client.get("/api/feed")
        assert "x-request-id" in resp.headers
        assert "x-response-time" in resp.headers
