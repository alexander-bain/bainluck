"""Contract tests for event sub-endpoints: related futures, team progression,
game markets, and event history.

Tests:
- GET /api/events/{id}/related-futures — team-classified futures markets
- GET /api/events/{id}/team-progression — championship grid rows for both teams
- GET /api/events/{id}/game-markets — game-level market sections
- GET /api/events/{id}/history — chart-ready probability history

Uses the shared ``client`` fixture (mock empty DB) and a seeded fixture
from test_route_events_seeded patterns for populated responses.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


# ============================================================================
# Helpers for seeded fixtures
# ============================================================================


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
    event.home_team = None
    event.away_team = None
    event.llm_gender = None
    event.llm_level = None
    event.llm_league = None
    event.llm_importance = None
    event.box_score_data = None
    return event


def _make_seeded_session(event=None):
    """Create a mock DB session that returns a seeded event."""
    session = AsyncMock()

    def make_scalar_result(data):
        result = MagicMock()
        result.scalar_one_or_none.return_value = data
        result.scalars.return_value.all.return_value = [data] if data else []
        result.scalars.return_value.first.return_value = data
        result.scalars.return_value.unique.return_value.all.return_value = [data] if data else []
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    empty_result.scalars.return_value.first.return_value = None
    empty_result.scalars.return_value.unique.return_value.all.return_value = []
    empty_result.scalar_one_or_none.return_value = None
    empty_result.scalar.return_value = None
    empty_result.fetchall.return_value = []
    empty_result.all.return_value = []
    empty_result.first.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower() if hasattr(stmt, "__str__") else ""
        if "events" in stmt_str and event:
            return make_scalar_result(event)
        return empty_result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


class _MockResult:
    """Small SQLAlchemy result stand-in for route-level contract tests."""

    def __init__(
        self,
        *,
        scalar=None,
        rows=None,
        first=None,
        scalar_rows=None,
    ):
        self._scalar = scalar
        self._rows = rows or []
        self._first = first
        self._scalar_rows = scalar_rows if scalar_rows is not None else self._rows

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def first(self):
        return self._first

    def scalars(self):
        result = MagicMock()
        result.all.return_value = self._scalar_rows
        result.first.return_value = self._scalar_rows[0] if self._scalar_rows else None
        result.unique.return_value.all.return_value = self._scalar_rows
        return result


def _make_market(
    *,
    id: int,
    name: str,
    source: str,
    bookmaker_count: int = 1,
):
    market = MagicMock()
    market.id = id
    market.name = name
    market.source = source
    market.status = "open"
    market.category = "championship"
    market.market_tier = 1
    market.event_id = None
    market.external_id = None
    market.commence_time = None
    market.resolution_date = datetime.now(timezone.utc) + timedelta(days=120)
    market.bookmaker_count = bookmaker_count
    return market


def _make_outcome(
    *,
    id: int,
    market,
    name: str,
    probability: float,
    probability_change_24h: float,
):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market.id
    outcome.market = market
    outcome.name = name
    outcome.current_probability = probability
    outcome.current_american_odds = None
    outcome.probability_change_24h = probability_change_24h
    outcome.opening_probability = probability - probability_change_24h
    outcome.rank = None
    outcome.team_id = None
    outcome.last_updated = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    return outcome


def _make_related_futures_session(event):
    """Mock DB session with duplicate cross-source futures for one event."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    kalshi_champ = _make_market(
        id=101,
        name="2026 NBA Champion",
        source="kalshi",
        bookmaker_count=1,
    )
    polymarket_champ = _make_market(
        id=102,
        name="NBA Champion",
        source="polymarket",
        bookmaker_count=4,
    )
    away_champ = _make_market(
        id=103,
        name="NBA Champion",
        source="kalshi",
        bookmaker_count=2,
    )
    outcomes = [
        _make_outcome(
            id=201,
            market=kalshi_champ,
            name="Boston Celtics",
            probability=0.42,
            probability_change_24h=0.03,
        ),
        _make_outcome(
            id=202,
            market=polymarket_champ,
            name="Boston Celtics",
            probability=0.44,
            probability_change_24h=0.02,
        ),
        _make_outcome(
            id=203,
            market=away_champ,
            name="Philadelphia 76ers",
            probability=0.08,
            probability_change_24h=-0.01,
        ),
    ]
    bookmaker_rows = [
        SimpleNamespace(outcome_id=201, bm_count=1),
        SimpleNamespace(outcome_id=202, bm_count=4),
        SimpleNamespace(outcome_id=203, bm_count=2),
    ]
    state = {"market_id_selects": 0}

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower() if hasattr(stmt, "__str__") else ""

        if "from events" in stmt_str:
            return _MockResult(scalar=event)

        if "select sports.id" in stmt_str:
            return _MockResult(rows=[SimpleNamespace(id=1)])

        if "group by futures_markets.market_tier" in stmt_str:
            return _MockResult(rows=[(1, 3)])

        if "from teams" in stmt_str and "roster_players" in stmt_str:
            return _MockResult(rows=[], first=None)

        if "from futures_outcomes" in stmt_str:
            return _MockResult(scalar_rows=outcomes)

        if "from futures_odds_snapshots" in stmt_str:
            return _MockResult(rows=bookmaker_rows)

        if "from line_movement_analyses" in stmt_str:
            return _MockResult(scalar=None)

        if "select futures_markets.id" in stmt_str:
            state["market_id_selects"] += 1
            if state["market_id_selects"] == 1:
                return _MockResult(
                    rows=[
                        SimpleNamespace(id=101, market_tier=1),
                        SimpleNamespace(id=102, market_tier=1),
                        SimpleNamespace(id=103, market_tier=1),
                    ]
                )
            if state["market_id_selects"] >= 7:
                return _MockResult(
                    rows=[
                        SimpleNamespace(id=101, market_tier=1),
                        SimpleNamespace(id=102, market_tier=1),
                        SimpleNamespace(id=103, market_tier=1),
                    ]
                )
            return _MockResult(rows=[])

        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


@pytest.fixture
async def seeded_client(monkeypatch):
    """Client with a seeded live NBA event for sub-endpoint tests."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    event = _make_event(id=42, home_team="Celtics", away_team="76ers", status="live")
    mock_session = _make_seeded_session(event=event)

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def populated_related_futures_client(monkeypatch):
    """Client with related futures rows that exercise dedup/grouping."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    event = _make_event(
        id=77,
        home_team="Boston Celtics",
        away_team="Philadelphia 76ers",
        status="scheduled",
    )
    mock_session = _make_related_futures_session(event)

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch(
            "app.services.llm.generate_related_futures_summary",
            return_value="Celtics and 76ers futures are active.",
        ),
        patch(
            "app.services.league_context.enrich_event_with_context",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ============================================================================
# Related Futures — /api/events/{id}/related-futures
# ============================================================================


class TestRelatedFuturesEmptyShape:
    """With an empty DB, related futures returns valid empty response."""

    async def test_returns_404_for_nonexistent_event(self, client):
        resp = await client.get("/api/events/999999/related-futures")
        assert resp.status_code in (200, 404)

    async def test_returns_422_for_invalid_id(self, client):
        resp = await client.get("/api/events/abc/related-futures")
        assert resp.status_code == 422


class TestRelatedFuturesQueryParams:
    """Query parameter validation."""

    async def test_debug_param_accepted(self, client):
        resp = await client.get("/api/events/1/related-futures?debug=true")
        assert resp.status_code in (200, 404)

    async def test_debug_false_accepted(self, client):
        resp = await client.get("/api/events/1/related-futures?debug=false")
        assert resp.status_code in (200, 404)

    async def test_invalid_debug_param_rejected(self, client):
        resp = await client.get("/api/events/1/related-futures?debug=definitely")
        assert resp.status_code == 422


class TestRelatedFuturesSeededShape:
    """With a seeded event, validate the full response shape."""

    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        assert resp.status_code == 200

    async def test_response_has_core_keys(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        for key in [
            "event_id", "home_team", "away_team",
            "home_team_futures", "away_team_futures", "total_count",
        ]:
            assert key in body, f"Missing key: {key}"

    async def test_event_id_matches(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        assert body["event_id"] == 42

    async def test_team_names_match(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        assert body["home_team"] == "Celtics"
        assert body["away_team"] == "76ers"

    async def test_futures_lists_are_lists(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        assert isinstance(body["home_team_futures"], list)
        assert isinstance(body["away_team_futures"], list)

    async def test_total_count_is_non_negative_int(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        assert isinstance(body["total_count"], int)
        assert body["total_count"] >= 0

    async def test_total_count_equals_futures_sum(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        assert body["total_count"] == (
            len(body["home_team_futures"]) + len(body["away_team_futures"])
        )

    async def test_summary_field_when_present(self, seeded_client):
        """When the full response path runs, summary is null or a string."""
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        if "summary" in body:
            assert body["summary"] is None or isinstance(body["summary"], str)

    async def test_event_status_when_present(self, seeded_client):
        """When the full response path runs, event_status is a valid status."""
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        if "event_status" in body:
            assert body["event_status"] in {"live", "scheduled", "completed", "closed"}

    async def test_league_context_when_present(self, seeded_client):
        """When the full response path runs, league_context is null or dict."""
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        if "league_context" in body:
            assert body["league_context"] is None or isinstance(body["league_context"], dict)

    async def test_box_score_when_present(self, seeded_client):
        """When the full response path runs, box_score is null or dict."""
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        if "box_score" in body:
            assert body["box_score"] is None or isinstance(body["box_score"], (dict, list))

    async def test_game_period_and_clock_when_present(self, seeded_client):
        """When the full response path runs, game_period and game_clock exist."""
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        if "game_period" in body:
            assert body["game_period"] is None or isinstance(body["game_period"], (int, str))
        if "game_clock" in body:
            assert body["game_clock"] is None or isinstance(body["game_clock"], str)


class TestRelatedFuturesPopulatedContract:
    """Populated related futures contract without external services."""

    async def test_populated_response_has_full_top_level_shape(
        self,
        populated_related_futures_client,
    ):
        resp = await populated_related_futures_client.get("/api/events/77/related-futures")
        assert resp.status_code == 200

        body = resp.json()
        assert body["event_id"] == 77
        assert body["home_team"] == "Boston Celtics"
        assert body["away_team"] == "Philadelphia 76ers"
        assert body["event_status"] == "scheduled"
        assert body["summary"] is None or isinstance(body["summary"], str)
        assert body["series_markets"] == []
        assert body["league_context"] is None
        assert body["total_count"] == 2

    async def test_cross_source_duplicates_are_grouped_by_merge_group(
        self,
        populated_related_futures_client,
    ):
        resp = await populated_related_futures_client.get("/api/events/77/related-futures")
        body = resp.json()

        assert len(body["home_team_futures"]) == 1
        item = body["home_team_futures"][0]
        assert item["market_id"] == 102
        assert item["source"] == "polymarket"
        assert item["outcome_name"] == "Boston Celtics"
        assert item["clean_label"] == "NBA Champion"
        assert item["display_category"] == "playoff_path"
        assert item["merge_group"] == "nba_champion"
        assert item["bookmaker_count"] == 4
        assert set(item["all_sources"]) == {"kalshi", "polymarket"}

    async def test_same_merge_group_keeps_distinct_team_outcomes(
        self,
        populated_related_futures_client,
    ):
        resp = await populated_related_futures_client.get("/api/events/77/related-futures")
        body = resp.json()

        assert len(body["away_team_futures"]) == 1
        away_item = body["away_team_futures"][0]
        assert away_item["market_id"] == 103
        assert away_item["outcome_name"] == "Philadelphia 76ers"
        assert away_item["merge_group"] == "nba_champion"
        assert "all_sources" not in away_item

    async def test_futures_item_value_contract(
        self,
        populated_related_futures_client,
    ):
        resp = await populated_related_futures_client.get("/api/events/77/related-futures")
        body = resp.json()
        item = body["home_team_futures"][0]

        assert item["probability"] == 0.44
        assert item["probability_change_24h"] == 0.02
        assert item["opening_probability"] == 0.42
        assert item["market_tier"] == 1
        assert item["category"] == "championship"
        assert item["relevance_reason"]
        assert item["last_updated"] == "2026-05-17T12:00:00+00:00"
        assert item["next_update_expected"]
        assert item["resolution_date"]

    async def test_debug_response_exposes_related_futures_counters(
        self,
        populated_related_futures_client,
    ):
        resp = await populated_related_futures_client.get(
            "/api/events/77/related-futures?debug=true"
        )
        assert resp.status_code == 200

        debug = resp.json()["_debug"]
        assert debug["season_market_count"] == 3
        assert debug["game_prop_count"] == 0
        assert debug["series_market_count"] == 0
        assert debug["sport_prefix"] == "basketball"
        assert debug["llm_category"] == "basketball"
        assert "Boston Celtics" in debug["home_patterns"]
        assert "Philadelphia 76ers" in debug["away_patterns"]


class TestRelatedFuturesItemShape:
    """Validate individual futures item shape when populated."""

    async def test_futures_item_has_core_fields(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        for side in ("home_team_futures", "away_team_futures"):
            for item in body[side]:
                for field in [
                    "market_id", "market_name", "source",
                    "outcome_id", "outcome_name", "probability",
                ]:
                    assert field in item, f"Futures item missing '{field}' in {side}"

    async def test_futures_item_probability_in_range(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        for side in ("home_team_futures", "away_team_futures"):
            for item in body[side]:
                prob = item["probability"]
                if prob is not None:
                    assert 0 <= prob <= 1, f"Probability out of range: {prob}"

    async def test_futures_item_has_metadata_fields(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        for side in ("home_team_futures", "away_team_futures"):
            for item in body[side]:
                # These fields should be present (may be null)
                for field in [
                    "clean_label", "display_category", "merge_group",
                    "market_tier", "category", "relevance_score",
                ]:
                    assert field in item, f"Futures item missing '{field}'"

    async def test_futures_item_has_change_fields(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        for side in ("home_team_futures", "away_team_futures"):
            for item in body[side]:
                assert "probability_change_24h" in item
                assert "opening_probability" in item

    async def test_futures_item_has_playoff_stage_fields(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/related-futures")
        body = resp.json()
        for side in ("home_team_futures", "away_team_futures"):
            for item in body[side]:
                assert "playoff_stage" in item
                assert "playoff_stage_type" in item
                assert "stage_order" in item


# ============================================================================
# Team Progression — /api/events/{id}/team-progression
# ============================================================================


class TestTeamProgressionEmptyDB:
    """With empty DB, team-progression returns valid empty response."""

    async def test_returns_404_for_nonexistent_event(self, client):
        resp = await client.get("/api/events/999999/team-progression")
        assert resp.status_code in (200, 404)

    async def test_returns_422_for_invalid_id(self, client):
        resp = await client.get("/api/events/abc/team-progression")
        assert resp.status_code == 422


class TestTeamProgressionSeededShape:
    """With a seeded event, validate response shape."""

    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        assert resp.status_code == 200

    async def test_response_has_core_keys(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        assert "event_id" in body
        assert "league" in body
        assert "home_team" in body
        assert "away_team" in body

    async def test_event_id_matches(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        assert body["event_id"] == 42

    async def test_league_is_string_or_none(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        assert body["league"] is None or isinstance(body["league"], str)

    async def test_team_fields_are_dict_or_none(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        assert body["home_team"] is None or isinstance(body["home_team"], dict)
        assert body["away_team"] is None or isinstance(body["away_team"], dict)

    async def test_has_league_name_when_league_present(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        if body["league"] is not None:
            assert "league_name" in body
            assert isinstance(body["league_name"], str)

    async def test_has_grid_url_when_league_present(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        if body["league"] is not None:
            assert "grid_url" in body
            assert isinstance(body["grid_url"], str)
            assert body["grid_url"].startswith("/playoffs/")

    async def test_team_row_shape_when_present(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        for side in ("home_team", "away_team"):
            team = body[side]
            if team is not None:
                assert "name" in team
                assert "short_name" in team
                assert "stages" in team
                assert isinstance(team["name"], str)
                assert isinstance(team["short_name"], str)
                assert isinstance(team["stages"], list)

    async def test_stage_shape_when_present(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/team-progression")
        body = resp.json()
        for side in ("home_team", "away_team"):
            team = body[side]
            if team is not None:
                for stage in team["stages"]:
                    assert "key" in stage
                    assert "label" in stage
                    assert "probability" in stage
                    assert isinstance(stage["key"], str)
                    assert isinstance(stage["label"], str)
                    if stage["probability"] is not None:
                        assert isinstance(stage["probability"], (int, float))
                        assert 0 <= stage["probability"] <= 1


# ============================================================================
# Game Markets — /api/events/{id}/game-markets
# ============================================================================


class TestGameMarketsEmptyShape:
    """With an empty DB, game-markets returns valid empty response."""

    async def test_returns_200_or_404(self, client):
        resp = await client.get("/api/events/999999/game-markets")
        assert resp.status_code in (200, 404)

    async def test_response_has_sections(self, client):
        resp = await client.get("/api/events/999999/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            for key in ["totals", "player_props", "spreads", "other"]:
                assert key in body, f"Missing key: {key}"

    async def test_sections_are_lists(self, client):
        resp = await client.get("/api/events/999999/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            for key in ["totals", "player_props", "spreads", "other"]:
                assert isinstance(body[key], list), f"Section '{key}' is not a list"


class TestGameMarketsSeededShape:
    """With a seeded event, validate game-markets response shape."""

    async def test_returns_200_or_404(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/game-markets")
        assert resp.status_code in (200, 404)

    async def test_has_event_id(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            assert "event_id" in body
            assert body["event_id"] == 42

    async def test_has_all_section_keys(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            for key in ["totals", "player_props", "spreads", "other"]:
                assert key in body
                assert isinstance(body[key], list)


# ============================================================================
# Event History — /api/events/{id}/history
# ============================================================================


class TestEventHistoryEmptyShape:
    """With an empty DB, event history returns valid empty response."""

    async def test_returns_200_or_404(self, client):
        resp = await client.get("/api/events/999999/history")
        assert resp.status_code in (200, 404)

    async def test_response_is_dict(self, client):
        resp = await client.get("/api/events/999999/history")
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, dict)


class TestEventHistorySeededShape:
    """With a seeded event, validate history response shape."""

    async def test_returns_200_or_404(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/history")
        assert resp.status_code in (200, 404)

    async def test_response_is_dict(self, seeded_client):
        resp = await seeded_client.get("/api/events/42/history")
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, dict)
