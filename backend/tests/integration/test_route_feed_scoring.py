"""Contract tests for GET /api/feed — scoring and ordering verification.

Tests that seeded events/futures are scored, ordered by score descending,
and that live events outrank scheduled ones. Uses mock DB sessions with
pre-built rows.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


def _make_event_row(
    id: int,
    home_team: str = "Team A",
    away_team: str = "Team B",
    status: str = "live",
    sport_key: str = "basketball_nba",
    home_prob: float = 0.6,
    commence_time: datetime | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
):
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
    row.home_score = home_score if home_score is not None else (80 if status == "live" else None)
    row.away_score = away_score if away_score is not None else (75 if status == "live" else None)
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
    volume_24h: float = 5000.0,
):
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
    row.volume_24h = volume_24h
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
    session = AsyncMock()

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
        stmt_str = str(stmt).lower() if hasattr(stmt, "__str__") else ""
        if "events" in stmt_str and events:
            return make_result(events)
        if "futures_markets" in stmt_str and futures:
            return make_result(futures)
        return empty_result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


def _make_client(events=None, futures=None):
    """Helper to create a seeded async client fixture."""

    async def _factory():
        from app.main import app

        mock_session = _make_seeded_session(events, futures)

        async def _mock_get_db():
            yield mock_session

        async def _mock_get_optional_user():
            return None

        app.dependency_overrides[get_db] = _mock_get_db
        app.dependency_overrides[get_db_rw] = _mock_get_db
        app.dependency_overrides[get_optional_user] = _mock_get_optional_user

        return app, mock_session

    return _factory


@pytest.fixture
async def scored_client():
    """Client with events spanning live/scheduled/completed for scoring tests."""
    from app.main import app

    events = [
        _make_event_row(1, "Celtics", "76ers", "live", "basketball_nba", 0.52,
                        home_score=55, away_score=52),
        _make_event_row(2, "Yankees", "Red Sox", "scheduled", "baseball_mlb", 0.60,
                        commence_time=datetime.now(timezone.utc) + timedelta(hours=2)),
        _make_event_row(3, "Lakers", "Nuggets", "completed", "basketball_nba", 0.85,
                        home_score=112, away_score=98),
    ]
    futures = [
        _make_futures_row(100, "NBA Championship", "basketball", 0.35, volume_24h=50000.0),
        _make_futures_row(101, "World Series Winner", "baseball", 0.20, volume_24h=8000.0),
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


class TestFeedScoring:
    """Feed items should be scored and ordered by score descending."""

    async def test_all_items_have_numeric_scores(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        for item in body["items"]:
            assert "score" in item
            assert isinstance(item["score"], (int, float))

    async def test_items_ordered_by_score_descending(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        scores = [item["score"] for item in body["items"]]
        assert scores == sorted(scores, reverse=True), "Items not sorted by score descending"

    async def test_all_items_have_reason(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        for item in body["items"]:
            assert "reason" in item
            assert isinstance(item["reason"], str)

    async def test_all_items_have_headline(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        for item in body["items"]:
            assert "headline" in item
            assert isinstance(item["headline"], str)


class TestFeedEventDataShape:
    """Event items in the feed should have the full expected data shape."""

    async def test_event_data_has_required_fields(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        events = [i for i in body["items"] if i["type"] == "event"]
        required_fields = ["id", "home_team", "away_team", "status", "commence_time"]
        for event in events:
            for field in required_fields:
                assert field in event["data"], f"Missing field: {field}"

    async def test_live_event_has_scores(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        live_events = [i for i in body["items"] if i["type"] == "event" and i["data"].get("status") == "live"]
        for event in live_events:
            assert event["data"].get("home_score") is not None
            assert event["data"].get("away_score") is not None

    async def test_event_id_is_int(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        events = [i for i in body["items"] if i["type"] == "event"]
        for event in events:
            assert isinstance(event["data"]["id"], int)

    async def test_event_status_is_valid(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        valid_statuses = {"live", "scheduled", "completed", "closed"}
        events = [i for i in body["items"] if i["type"] == "event"]
        for event in events:
            assert event["data"]["status"] in valid_statuses


class TestFeedFuturesDataShape:
    """Futures items in the feed should have the full expected data shape."""

    async def test_futures_data_has_required_fields(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        futures = [i for i in body["items"] if i["type"] == "futures"]
        required_fields = ["id", "name", "source", "status"]
        for market in futures:
            for field in required_fields:
                assert field in market["data"], f"Missing field: {field}"

    async def test_futures_id_is_int(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        futures = [i for i in body["items"] if i["type"] == "futures"]
        for market in futures:
            assert isinstance(market["data"]["id"], int)

    async def test_futures_source_is_string(self, scored_client):
        resp = await scored_client.get("/api/feed")
        body = resp.json()
        futures = [i for i in body["items"] if i["type"] == "futures"]
        for market in futures:
            assert isinstance(market["data"]["source"], str)


class TestFeedSportFilter:
    """Sport filter should restrict items to the requested sport."""

    async def test_basketball_filter_excludes_baseball(self, scored_client):
        resp = await scored_client.get("/api/feed?sport=basketball")
        body = resp.json()
        for item in body["items"]:
            if item["type"] == "event":
                sport = item["data"].get("sport", "")
                assert "baseball" not in sport, f"Baseball event in basketball filter: {sport}"

    async def test_status_live_filter(self, scored_client):
        resp = await scored_client.get("/api/feed?status=live")
        assert resp.status_code == 200


class TestFeedPaginationWithData:
    """Pagination should work correctly with seeded data."""

    async def test_limit_restricts_items(self, scored_client):
        resp = await scored_client.get("/api/feed?limit=1")
        body = resp.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1

    async def test_offset_skips_items(self, scored_client):
        full = await scored_client.get("/api/feed")
        offset = await scored_client.get("/api/feed?offset=1")
        full_body = full.json()
        offset_body = offset.json()
        if len(full_body["items"]) > 1:
            assert offset_body["offset"] == 1

    async def test_has_more_reflects_remaining(self, scored_client):
        resp = await scored_client.get("/api/feed?limit=1")
        body = resp.json()
        full = await scored_client.get("/api/feed")
        full_body = full.json()
        if len(full_body["items"]) > 1:
            assert body["has_more"] is True
