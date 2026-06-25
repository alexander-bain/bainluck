"""Contract tests for GET /api/events/{id} with seeded mock data.

Tests the full event detail response shape, related futures structure,
and game-markets sections when the DB returns pre-built event rows.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


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
    event.win_probability_sources = {
        "betting": {"value": home_prob, "home_probability": home_prob},
        "espn": 0.62,
    }
    event.current_home_probability = home_prob
    event.current_away_probability = 1 - home_prob
    event.espn_game_id = None
    event.espn_id = f"espn-{id}"
    event.espn_data = None
    event.espn_win_prob_home = 0.62
    event.game_clock = "6:32"
    event.period = "3rd Quarter"
    event.broadcast_info = "ESPN"
    event.event_tags = ["narrative:rivalry", "legacy:ignored"]
    event.pulse_score = None
    event.pulse_label = None
    event.excite_index = None
    event.raw_ei = None
    event.ei_metadata = None
    event.home_team_id = None
    event.away_team_id = None
    event.llm_gender = None
    event.llm_level = "professional"
    event.llm_league = "NBA"
    event.llm_importance = "regular"
    event.opening_home_probability = 0.58
    event.opening_away_probability = 0.42
    event.opening_favorite = home_team
    event.box_score_data = {
        "players": [
            {"name": "Jayson Tatum", "team": home_team, "points": 31},
        ],
    }
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
    market.sport_id = 1
    market.volume_24h = 5000.0
    market.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    market.resolution_date = datetime.now(timezone.utc) + timedelta(days=60)
    market.image_url = None
    market.hook_description = None
    market.external_id = f"{source}-{id}"
    market.canonical_market_key = None
    market.outcome_count = 10
    market.group_id = None
    market.group_type = None
    market.market_type = None
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
    outcome.current_probability = probability
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
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(id=1, home_team="Celtics", away_team="76ers", status="live")
    mock_session = _make_event_detail_session(event=event)

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

    _game_markets_cache.clear()
    app.dependency_overrides.clear()


@pytest.fixture
async def game_markets_client():
    """Client with a seeded event plus linked game markets and outcomes."""
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(id=2, home_team="Celtics", away_team="76ers", status="live")
    total_market = _make_futures_market(
        id=201,
        name="Celtics at 76ers Total Points",
        source="kalshi",
    )
    spread_market = _make_futures_market(
        id=202,
        name="Celtics at 76ers Spread",
        source="kalshi",
    )
    player_market = _make_futures_market(
        id=203,
        name="Celtics at 76ers: Jayson Tatum Points",
        source="kalshi",
    )
    period_market = _make_futures_market(
        id=204,
        name="Celtics at 76ers Total Points",
        source="kalshi",
    )
    period_market.external_id = "KXNBA2HTOTAL-26MAY17BOSPHI"
    markets = [total_market, spread_market, player_market, period_market]
    for market in markets:
        market.event_id = event.id

    outcomes = [
        _make_outcome(id=301, market_id=201, name="Over 224.5", probability=0.57),
        _make_outcome(id=302, market_id=202, name="Celtics -4.5", probability=0.54),
        _make_outcome(id=303, market_id=203, name="Jayson Tatum: 30+", probability=0.41),
        _make_outcome(id=304, market_id=204, name="Over 105.5", probability=0.52),
    ]
    mock_session = _make_event_detail_session(
        event=event,
        futures=markets,
        outcomes=outcomes,
    )

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

    _game_markets_cache.clear()
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

    async def test_nested_espn_contract(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        espn = body["espn"]
        assert espn["espn_id"] == "espn-1"
        assert espn["game_clock"] == "6:32"
        assert espn["broadcast"] == "ESPN"
        assert espn["win_probability"] == 0.62
        assert "probability_sources" in espn

    async def test_win_probability_sources_include_display_metadata(
        self, event_detail_client
    ):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        betting = body["win_probability_sources"]["betting"]
        assert betting["value"]["home_probability"] == 0.65
        assert betting["display_name"] == "Betting Odds"
        assert betting["type"] == "market"
        assert betting["color"].startswith("#")

    async def test_optional_nested_detail_blocks(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert body["metadata"] == {
            "gender": None,
            "level": "professional",
            "league": "NBA",
            "importance": "regular",
        }
        assert body["opening_odds"] == {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "favorite": "Celtics",
        }
        assert body["box_score_data"]["players"][0]["name"] == "Jayson Tatum"
        assert "narrative:rivalry" in body["event_tags"]


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

    async def test_aggregate_current_odds_fallback_contract(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1")
        body = resp.json()
        assert body["current_odds"] == {
            "home_probability": 0.64,
            "away_probability": 0.36,
            "source": "aggregate",
            "bookmaker_count": 0,
        }


class TestEventDetailNotFound:
    """Non-existent events should return 404."""

    async def test_404_for_missing_event(self, client):
        resp = await client.get("/api/events/999999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"] == "Event not found"

    async def test_422_for_non_integer_event_id(self, client):
        resp = await client.get("/api/events/not-an-id")
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"][0]["loc"][-1] == "event_id"


class TestGameMarketsShape:
    """GET /api/events/{id}/game-markets should have structured sections."""

    async def test_returns_200_or_404(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/game-markets")
        assert resp.status_code in (200, 404)

    async def test_sections_present_on_200(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            for section in ["totals", "player_props", "spreads", "matchups", "other"]:
                assert section in body, f"Missing section: {section}"
            assert isinstance(body["totals"], list)
            assert isinstance(body["player_props"], list)
            assert isinstance(body["spreads"], list)
            assert isinstance(body["matchups"], list)
            assert isinstance(body["other"], list)

    async def test_has_event_context(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            assert body.get("event_id") == 1

    async def test_404_for_missing_event(self, client):
        resp = await client.get("/api/events/999999/game-markets")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Event not found"

    async def test_422_for_non_integer_event_id(self, client):
        resp = await client.get("/api/events/not-an-id/game-markets")
        assert resp.status_code == 422


class TestGameMarketsPopulatedShape:
    """Seeded linked markets should populate typed game-market sections."""

    async def test_populated_sections_have_event_context(self, game_markets_client):
        resp = await game_markets_client.get("/api/events/2/game-markets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == 2
        assert body["home_team"] == "Celtics"
        assert body["away_team"] == "76ers"
        assert body["status"] == "live"
        assert body["home_score"] == 88
        assert body["away_score"] == 82

    async def test_total_market_item_contract(self, game_markets_client):
        resp = await game_markets_client.get("/api/events/2/game-markets")
        total = resp.json()["totals"][0]
        assert total["threshold"] == 224.5
        assert total["over_probability"] == 0.57
        assert total["source"] == "kalshi"
        assert total["market_type"] == "game_total"
        assert total["market_name"] == "Celtics at 76ers Total Points"
        assert total["outcome_name"] == "Over 224.5"
        assert total["movement"] == 0.05

    async def test_player_prop_item_contract(self, game_markets_client):
        resp = await game_markets_client.get("/api/events/2/game-markets")
        prop = resp.json()["player_props"][0]
        assert prop["market_name"] == "Celtics at 76ers: Jayson Tatum Points"
        assert prop["outcome_name"] == "Jayson Tatum: 30+"
        assert prop["threshold"] == 30.0
        assert prop["over_probability"] == 0.41
        assert prop["opening_over_probability"] == 0.36
        assert prop["movement"] == 0.05

    async def test_spread_and_period_market_contracts(self, game_markets_client):
        resp = await game_markets_client.get("/api/events/2/game-markets")
        body = resp.json()
        spread = body["spreads"][0]
        assert spread == {
            "market_name": "Celtics at 76ers Spread",
            "outcome_name": "Celtics -4.5",
            "threshold": 4.5,
            "probability": 0.54,
            "source": "kalshi",
        }
        period = body["period_markets"][0]
        assert period["market_type"] == "half_total"
        assert period["period"] == "2H"
        assert period["threshold"] == 105.5
        assert period["over_probability"] == 0.52

    async def test_empty_sections_and_pace_keep_stable_types(self, game_markets_client):
        resp = await game_markets_client.get("/api/events/2/game-markets")
        body = resp.json()
        assert body["team_totals"] == []
        assert body["other"] == []
        assert body["pace"] == {
            "total_scored": 170,
            "projected_total": 277,
            "fraction_elapsed": 0.614,
            "time_remaining_display": "18:31 left",
        }


@pytest.fixture
async def no_price_markets_client():
    """Event with a real total market + a no-real-price market + a placeholder-
    team market — only the real one should render (#921 slice 2)."""
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(id=3, home_team="Celtics", away_team="76ers", status="live")
    real_market = _make_futures_market(
        id=401, name="Celtics at 76ers Total Points", source="kalshi"
    )
    no_price_market = _make_futures_market(
        id=402, name="Celtics at 76ers Total Rebounds", source="kalshi"
    )
    placeholder_market = _make_futures_market(
        id=403, name="TBD vs TBD Total Points", source="kalshi"
    )
    markets = [real_market, no_price_market, placeholder_market]
    for market in markets:
        market.event_id = event.id

    outcomes = [
        # real: top outcome well above the 0.5% floor → kept
        _make_outcome(id=501, market_id=401, name="Over 224.5", probability=0.57),
        # no real price: top outcome 0.3% (<0.5%) → dropped
        _make_outcome(id=502, market_id=402, name="Over 44.5", probability=0.003),
        # placeholder teams → dropped (even with a real price)
        _make_outcome(id=503, market_id=403, name="Over 200.5", probability=0.55),
    ]
    mock_session = _make_event_detail_session(
        event=event, futures=markets, outcomes=outcomes
    )

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

    _game_markets_cache.clear()
    app.dependency_overrides.clear()


class TestGameMarketsNoRealPriceDrop:
    """#921 slice 2: no-real-price + placeholder-team markets must not render on
    event pages; legitimate priced markets stay."""

    async def test_real_market_kept_junk_dropped(self, no_price_markets_client):
        resp = await no_price_markets_client.get("/api/events/3/game-markets")
        assert resp.status_code == 200
        body = resp.json()
        # Collect every market_name across all sections.
        names = set()
        for section in body.values():
            if isinstance(section, list):
                for item in section:
                    if isinstance(item, dict) and item.get("market_name"):
                        names.add(item["market_name"])
        assert "Celtics at 76ers Total Points" in names  # real → kept
        assert "Celtics at 76ers Total Rebounds" not in names  # no price → dropped
        assert "TBD vs TBD Total Points" not in names  # placeholder → dropped


@pytest.fixture
async def deep_otm_spread_client():
    """Event with a spread market carrying a near-the-money line + deep-OTM
    alternate rungs — only the meaningful lines should render (#921 residual)."""
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(id=4, home_team="Celtics", away_team="76ers", status="live")
    spread_market = _make_futures_market(
        id=601, name="Celtics at 76ers Spread", source="kalshi"
    )
    spread_market.event_id = event.id
    markets = [spread_market]

    outcomes = [
        _make_outcome(id=701, market_id=601, name="Celtics -1.5", probability=0.46),  # near-money → kept
        _make_outcome(id=702, market_id=601, name="Celtics +1.5", probability=0.54),  # near-money → kept
        _make_outcome(id=703, market_id=601, name="Celtics -12.5", probability=0.001),  # deep-OTM → dropped
        _make_outcome(id=704, market_id=601, name="Celtics -15.5", probability=0.001),  # deep-OTM → dropped
    ]
    mock_session = _make_event_detail_session(
        event=event, futures=markets, outcomes=outcomes
    )

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

    _game_markets_cache.clear()
    app.dependency_overrides.clear()


class TestDeepOtmSpreadCollapse:
    """#921 residual: deep-OTM alternate spread rungs (cover prob < 2%) are
    collapsed; near-the-money lines stay."""

    async def test_deep_otm_rungs_dropped_near_money_kept(self, deep_otm_spread_client):
        resp = await deep_otm_spread_client.get("/api/events/4/game-markets")
        assert resp.status_code == 200
        spreads = resp.json()["spreads"]
        names = {s["outcome_name"] for s in spreads}
        assert "Celtics -1.5" in names  # 46% near-money → kept
        assert "Celtics +1.5" in names  # 54% near-money → kept
        assert "Celtics -12.5" not in names  # 0.1% deep-OTM → dropped
        assert "Celtics -15.5" not in names  # 0.1% deep-OTM → dropped
        # every surviving spread line is at or above the 2% floor
        assert all(
            s["probability"] is None or s["probability"] >= 0.02 for s in spreads
        )


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

    async def test_empty_related_futures_contract(self, event_detail_client):
        resp = await event_detail_client.get("/api/events/1/related-futures")
        assert resp.status_code == 200
        assert resp.json() == {
            "event_id": 1,
            "home_team": "Celtics",
            "away_team": "76ers",
            "home_team_futures": [],
            "away_team_futures": [],
            "series_markets": [],
            "total_count": 0,
        }

    async def test_404_for_missing_event(self, client):
        resp = await client.get("/api/events/999999/related-futures")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Event not found"

    async def test_422_for_non_integer_event_id(self, client):
        resp = await client.get("/api/events/not-an-id/related-futures")
        assert resp.status_code == 422


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
