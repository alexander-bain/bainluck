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
    row.home_team_name = home_team
    row.away_team_name = away_team
    row.status = status
    row.sport_key = sport_key
    row.sport_id = 1
    row.sport_name = "Basketball"
    row.sport = MagicMock()
    row.sport.key = sport_key
    row.sport.name = row.sport_name
    row.commence_time = commence_time or (datetime.now(timezone.utc) - timedelta(hours=1))
    row.completed_at = None
    row.home_score = 80 if status == "live" else None
    row.away_score = 75 if status == "live" else None
    row.external_id = f"ext-{id}"
    row.win_probability_sources = {"betting": {"home_probability": home_prob}}
    row.current_home_probability = home_prob
    row.current_away_probability = 1 - home_prob
    row.opening_home_probability = max(0.01, home_prob - 0.25)
    row.opening_away_probability = 1 - row.opening_home_probability
    row.opening_home_spread = None
    row.opening_over_under = None
    row.opening_favorite = None
    row.espn_game_id = None
    row.espn_data = None
    row.event_tags = []
    row.pulse_score = None
    row.pulse_label = None
    row.excite_index = None
    row.raw_ei = None
    row.ei_metadata = None
    row.llm_importance = None
    row.llm_gender = None
    row.llm_level = None
    row.llm_league = None
    row.broadcast_info = None
    row.period = "Q3" if status == "live" else None
    row.game_clock = "5:00" if status == "live" else None
    row.statpal_end_time = None
    row.home_team_id = None
    row.away_team_id = None
    return row


def _make_outcome_row(
    id: int,
    name: str,
    probability: float,
    rank: int,
    movement: float | None = None,
):
    """Build a mock FuturesOutcome row."""
    row = MagicMock()
    row.id = id
    row.name = name
    row.current_probability = probability
    row.probability_change_24h = movement
    row.rank = rank
    row.rank_change_24h = None
    row.opening_probability = max(0.01, probability - 0.03)
    row.team_id = None
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
    row.updated_at = datetime.now(timezone.utc)
    row.image_url = None
    row.hook_description = None
    row.hook_generated_at = None
    row.hook_leader_at_generation = None
    row.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    row.market_metadata = {}
    row.llm_league = None
    row.llm_gender = None
    row.llm_level = None
    row.external_id = f"kalshi-{id}"
    row.canonical_market_key = None
    row.group_type = None
    row.group_id = None
    row.leader_name = "Celtics"
    row.leader_probability = leader_prob
    row.leader_movement = 0.03
    row.sport = MagicMock()
    row.sport.key = f"{sport_category}_seeded"
    row.sport.name = sport_category.capitalize()
    row.outcomes = [
        _make_outcome_row(id * 10 + 1, row.leader_name, leader_prob, 1, 0.04),
        _make_outcome_row(id * 10 + 2, "Nuggets", 0.25, 2, -0.02),
        _make_outcome_row(id * 10 + 3, "Yankees", 0.18, 3, 0.01),
    ]
    row.outcome_count = len(row.outcomes)
    row.source_count = 1
    row.top_outcomes = []
    return row


def _make_seeded_session(events=None, futures=None):
    """Create a mock DB session that returns seeded events and futures."""
    session = AsyncMock()
    call_count = 0

    def make_result(data):
        result = MagicMock()
        scalar_result = MagicMock()
        scalar_result.all.return_value = data or []
        scalar_result.first.return_value = (data or [None])[0] if data else None
        scalar_result.unique.return_value.all.return_value = data or []
        result.scalars.return_value = scalar_result
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
        normalized_stmt = " ".join(stmt_str.split())
        if "from events" in normalized_stmt and events:
            return make_result(events)
        if "from futures_markets" in normalized_stmt and futures:
            if normalized_stmt.startswith("select futures_markets.id from futures_markets"):
                return make_result([market.id for market in futures])
            return make_result(futures)
        return empty_result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


@pytest.fixture
async def seeded_client():
    """Client with seeded events and futures data."""
    from app.main import app

    events = [
        _make_event_row(1, "Celtics", "76ers", "live", "basketball_nba", 0.51),
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

    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=RuntimeError("feed cache disabled in seeded route tests"),
        ),
        patch("app.routes.feed._score_golf_tournaments", new=AsyncMock(return_value=[])),
    ):
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

    async def test_response_shape_exposes_public_item_contract(self, seeded_client):
        resp = await seeded_client.get("/api/feed?limit=5")
        body = resp.json()

        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 5
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

        for item in body["items"]:
            assert not any(key.startswith("_") for key in item)
            assert {"type", "score", "reason", "headline", "data"} <= set(item)
            assert 0 <= item["score"] <= 100
            assert isinstance(item["reason"], str)
            assert isinstance(item["data"], dict)

    async def test_pagination_returns_stable_ordered_slice(self, seeded_client):
        full_resp = await seeded_client.get("/api/feed?include_futures=false&limit=10")
        page_resp = await seeded_client.get("/api/feed?include_futures=false&limit=2&offset=1")

        full = full_resp.json()
        page = page_resp.json()

        expected_slice = full["items"][1:3]
        assert page["items"] == expected_slice
        assert page["total"] == full["total"]
        assert page["limit"] == 2
        assert page["offset"] == 1
        assert page["has_more"] == ((1 + 2) < full["total"])

    async def test_event_item_nested_fields_are_stable(self, seeded_client):
        resp = await seeded_client.get("/api/feed?include_futures=false&limit=5")
        body = resp.json()

        event = next(item for item in body["items"] if item["type"] == "event")
        data = event["data"]

        assert {
            "id",
            "external_id",
            "sport",
            "sport_name",
            "home_team",
            "away_team",
            "commence_time",
            "status",
            "home_score",
            "away_score",
            "current_odds",
            "win_probability_sources",
            "event_tags",
        } <= set(data)
        assert data["home_team"]
        assert data["away_team"]
        assert data["current_odds"]["home_probability"] + data["current_odds"]["away_probability"] == pytest.approx(1.0)
        assert "betting" in data["win_probability_sources"]
        assert isinstance(data["event_tags"], list)

    async def test_futures_item_nested_fields_are_stable(self, seeded_client):
        resp = await seeded_client.get("/api/feed?include_events=false&limit=5")
        body = resp.json()

        futures = next(
            item
            for item in body["items"]
            if item["type"] == "futures" and item["data"]["id"] == 100
        )
        data = futures["data"]

        assert {
            "id",
            "name",
            "source",
            "sources",
            "source_count",
            "market_tier",
            "status",
            "resolution_date",
            "top_outcomes",
            "outcome_count",
            "market_tags",
        } <= set(data)
        assert data["source"] == "kalshi"
        assert data["sources"] == ["kalshi"]
        assert data["outcome_count"] == 3
        assert [outcome["rank"] for outcome in data["top_outcomes"]] == [1, 2, 3]
        assert [outcome["name"] for outcome in data["top_outcomes"]] == [
            "Celtics",
            "Nuggets",
            "Yankees",
        ]
        for outcome in data["top_outcomes"]:
            assert {"id", "name", "probability", "rank", "movement"} <= set(outcome)
            assert 0 <= outcome["probability"] <= 1
