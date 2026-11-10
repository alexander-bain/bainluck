"""#11666 Step 5c — `other` rows in `GET /api/events/{id}/game-markets` emit `pregame_mark`.

Rows classified under `"other"` — notably MLB extra innings ("Will the game go to
extra innings?", `KXMLBEXTRA`) — previously carried `opening_probability` only,
while `spreads`, `totals`, `team_totals`, `period_markets`, and `player_props`
resolved `pregame_mark` via `_resolve_pregame_mark(market, o, True, False, ...)`.
Both `other_markets.append` sites in `backend/app/routes/events.py` (the primary
`"other"` branch and the #6769 range-guard rescue branch) now include
`pregame_mark` so native and web readers keep the pregame mark after first pitch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 15411666


def _build_mlb_extra_innings_fixture():
    commence = datetime.now(timezone.utc) - timedelta(hours=1)
    event = _make_event(
        id=EVENT_ID,
        home_team="New York Yankees",
        away_team="Boston Red Sox",
        status="live",
        sport_key="baseball_mlb",
        home_score=3,
        away_score=3,
    )
    event.llm_league = "MLB"
    event.period = "Bot 8th"
    event.commence_time = commence

    # 1. Primary "other" market with a valid pre-first-pitch pregame_mark pin (0.095)
    #    distinct from opening_probability (0.12) and live probability (0.31).
    extra_innings = _make_futures_market(
        id=1901,
        name="Boston at New York: Extra Innings",
        source="kalshi",
    )
    extra_innings.status = "open"
    extra_innings.event_id = EVENT_ID
    extra_innings.market_metadata = {
        "pregame_mark": {
            "captured_at": (commence - timedelta(minutes=6)).isoformat(),
            "price_observed_at": (commence - timedelta(minutes=6, seconds=10)).isoformat(),
            "commence_time": commence.isoformat(),
            "outcomes": {"19101": 0.095},
        }
    }

    # 2. Primary "other" market whose pin was observed AFTER first pitch (0.64) —
    #    must be refused by `_resolve_pregame_mark` and fall back to opening (0.11).
    late_pin_other = _make_futures_market(
        id=1902,
        name="Boston at New York: Walk-off Win",
        source="kalshi",
    )
    late_pin_other.status = "open"
    late_pin_other.event_id = EVENT_ID
    late_pin_other.market_metadata = {
        "pregame_mark": {
            "captured_at": (commence + timedelta(minutes=15)).isoformat(),
            "price_observed_at": (commence + timedelta(minutes=14, seconds=50)).isoformat(),
            "commence_time": commence.isoformat(),
            "outcomes": {"19201": 0.64},
        }
    }

    # 3. #6769 range-guard rescue into `other_markets`: market name classifies as
    #    "totals" ("Total Runs"), but outcome is a range bucket ("7-8 runs") with
    #    no Over/Under line, so the route rescues it into `other_markets`.
    rescued_range = _make_futures_market(
        id=1903,
        name="Boston at New York: Total Runs Band",
        source="kalshi",
    )
    rescued_range.status = "open"
    rescued_range.event_id = EVENT_ID
    rescued_range.market_metadata = {
        "pregame_mark": {
            "captured_at": (commence - timedelta(minutes=8)).isoformat(),
            "price_observed_at": (commence - timedelta(minutes=8, seconds=5)).isoformat(),
            "commence_time": commence.isoformat(),
            "outcomes": {"19301": 0.235},
        }
    }

    o_extra = _make_outcome(
        id=19101,
        market_id=1901,
        name="Yes",
        probability=0.31,
    )
    o_extra.opening_probability = 0.12

    o_late = _make_outcome(
        id=19201,
        market_id=1902,
        name="Yes",
        probability=0.45,
    )
    o_late.opening_probability = 0.11

    o_rescued = _make_outcome(
        id=19301,
        market_id=1903,
        name="7 to 8 runs",
        probability=0.28,
    )
    o_rescued.opening_probability = 0.20

    return (
        event,
        [extra_innings, late_pin_other],
        [o_extra, o_late],
    )


@pytest.mark.asyncio
async def test_other_markets_emit_resolved_pregame_mark_on_game_markets_route():
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _build_mlb_extra_innings_fixture()
    mock_session = _make_event_detail_session(
        event=event, futures=futures, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/events/{EVENT_ID}/game-markets")
        assert resp.status_code == 200
        payload = resp.json()
        other_rows = {row["market_name"]: row for row in payload.get("other", [])}

        # 1. Valid pre-first-pitch pin is served on `pregame_mark` for MLB extra innings.
        assert "Boston at New York: Extra Innings" in other_rows
        extra = other_rows["Boston at New York: Extra Innings"]
        assert extra["probability"] == 0.31
        assert extra["pregame_mark"] == 0.095

        # 2. In-play pin is rejected; `pregame_mark` falls back to `opening_probability`.
        assert "Boston at New York: Walk-off Win" in other_rows
        late = other_rows["Boston at New York: Walk-off Win"]
        assert late["probability"] == 0.45
        assert late["pregame_mark"] == 0.11
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()


@pytest.mark.asyncio
async def test_range_rescued_other_market_emits_pregame_mark_on_settled_event():
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    now = datetime.now(timezone.utc)
    commence = now - timedelta(hours=4)
    event = _make_event(
        id=EVENT_ID + 1,
        sport_key="americanfootball_nfl",
    )
    event.name = "Buffalo Bills at Houston Texans"
    event.status = "completed"
    event.commence_time = commence
    event.home_team_name = "Houston Texans"
    event.away_team_name = "Buffalo Bills"
    event.home_score = 23
    event.away_score = 20

    rescued_td = _make_futures_market(
        id=1903,
        name="Buffalo vs Houston: Total Touchdowns",
        source="kalshi",
    )
    rescued_td.external_id = "KXNFLTD-26NOV08BUFHOU-T4"
    rescued_td.status = "resolved"
    rescued_td.event_id = EVENT_ID + 1
    rescued_td.market_metadata = {
        "pregame_mark": {
            "captured_at": (commence - timedelta(minutes=8)).isoformat(),
            "observed_at": (commence - timedelta(minutes=8, seconds=5)).isoformat(),
            "commence_time": commence.isoformat(),
            "outcomes": {"19301": 0.235},
        }
    }
    o_rescued = _make_outcome(
        id=19301,
        market_id=1903,
        name="Over 4.5 touchdowns",
        probability=0.99,
        is_winner=True,
        resolution_source="api_settlement",
    )
    o_rescued.opening_probability = 0.20

    mock_session = _make_event_detail_session(
        event=event, futures=[rescued_td], outcomes=[o_rescued]
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/events/{EVENT_ID + 1}/game-markets")
        assert resp.status_code == 200
        payload = resp.json()
        other_rows = {row["market_name"]: row for row in payload.get("other", [])}
        assert "Buffalo vs Houston: Total Touchdowns" in other_rows
        rescued = other_rows["Buffalo vs Houston: Total Touchdowns"]
        assert rescued["pregame_mark"] == 0.235
        assert rescued["is_winner"] is True
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()
