"""#10090 — Team Championship Path live refresh endpoint and candidate market IDs."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.main import app
from app.routes import teams as teams_route
from app.routes.teams import _get_championship_path
from app.services.database import get_db
from app.utils import rate_limit as limits


def _mock_outcome(outcome_id: int, prob: float, *, name: str = "Lakers", rank: int = 1):
    return SimpleNamespace(
        id=outcome_id,
        outcome_name=name,
        current_probability=prob,
        probability_change_24h=0.01,
        rank=rank,
    )


def _mock_market(
    market_id: int,
    name: str,
    tier: int,
    *,
    source: str = "kalshi",
    group_id: str | None = None,
    sport_category: str = "basketball",
):
    return SimpleNamespace(
        id=market_id,
        name=name,
        market_tier=tier,
        source=source,
        group_id=group_id,
        llm_sport_category=sport_category,
        external_id=f"EXT-{market_id}",
        market_metadata=None,
    )


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.first.return_value = items[0] if items else None
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    result.all.return_value = items
    result.first.return_value = items[0] if items else None
    return result


class _RowsDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        res = SimpleNamespace()
        res.all = lambda: self._rows
        return res


@pytest.fixture
def _team_route_client(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    empty = _scalars_result([])
    mock_db = AsyncMock()
    mock_db.execute.return_value = empty

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    return mock_db


def _clear_overrides():
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_championship_path_emits_market_ids_components_and_withheld_stream_ids():
    rows = [
        # Tier 1 agreed multi-venue blend
        (_mock_outcome(101, 0.20), _mock_market(1001, "NBA Champion 2027", 1, source="kalshi")),
        (_mock_outcome(102, 0.24), _mock_market(1002, "Pro Basketball Champion", 1, source="polymarket")),
        # Tier 4 disagrees beyond 0.25 -> step withheld, but candidate market_ids still tracked
        (_mock_outcome(201, 0.10), _mock_market(2001, "Pacific Division Winner", 4, source="kalshi")),
        (_mock_outcome(202, 0.55), _mock_market(2002, "Pacific Division Winner", 4, source="polymarket")),
    ]
    tracked: set[int] = set()
    now = datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)
    path = await _get_championship_path(
        42,
        _RowsDB(rows),
        league_slug="nba",
        now=now,
        team_sport_key="basketball_nba",
        out_market_ids=tracked,
    )

    assert len(path) == 1
    step = path[0]
    assert step["tier"] == 1
    assert step["probability"] == pytest.approx(0.22)
    assert step["market_ids"] == [1001, 1002]
    assert step["components"] == [
        {"market_id": 1001, "outcome_id": 101, "source": "kalshi", "probability": 0.2, "observed_at": None},
        {"market_id": 1002, "outcome_id": 102, "source": "polymarket", "probability": 0.24, "observed_at": None},
    ]
    assert tracked == {1001, 1002, 2001, 2002}


@pytest.mark.asyncio
async def test_championship_path_route_matches_get_team_and_stamps_grid_verdict(_team_route_client):
    from tests.integration.test_route_teams import _mock_team

    mock_db = _team_route_client
    team = _mock_team()
    rows = [
        (_mock_outcome(101, 0.18), _mock_market(501, "NBA Champion 2027", 1, source="kalshi")),
        (_mock_outcome(102, 0.22), _mock_market(502, "NBA Finals Winner", 1, source="polymarket")),
    ]
    grid_payload = {
        "season": "2026-27",
        "columns": [{"key": "championship", "market_ids": [501]}],
        "teams": [
            {
                "team_id": team.id,
                "cells": {"championship": {"state": "eliminated"}},
            }
        ],
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch.object(teams_route, "_read_cached_grid", AsyncMock(return_value=grid_payload)),
                patch.object(
                    teams_route,
                    "_club_row_identity",
                    AsyncMock(return_value=(frozenset({team.id}), frozenset({team.name}))),
                ),
                patch.object(
                    teams_route,
                    "datetime",
                    SimpleNamespace(now=lambda tz=None: datetime(2026, 11, 24, tzinfo=timezone.utc)),
                ),
            ):
                mock_db.execute.side_effect = [
                    _scalars_result([team]),
                    _scalars_result([]),  # all_sports
                    _scalars_result([]),  # upcoming events
                    _scalars_result([]),  # recent events
                    _scalars_result([]),  # futures
                    _scalars_result(rows),  # championship path
                ]
                full_resp = await client.get("/api/teams/lakers")

                mock_db.execute.side_effect = [
                    _scalars_result([team]),
                    _scalars_result([]),  # all_sports
                    _scalars_result(rows),  # championship path
                ]
                path_resp = await client.get("/api/teams/lakers/championship-path")
    finally:
        _clear_overrides()

    assert full_resp.status_code == 200
    assert path_resp.status_code == 200
    assert path_resp.headers.get("cache-control") == "no-store"

    full_body = full_resp.json()
    path_body = path_resp.json()
    assert path_body["team_id"] == team.id
    assert path_body["championship_path"] == full_body["championship_path"]
    assert path_body["stream_market_ids"] == full_body["championship_path_market_ids"] == [501, 502]
    assert path_body["championship_path"][0]["state"] == "eliminated"
    assert isinstance(path_body["built_at"], (int, float))


@pytest.mark.asyncio
async def test_championship_path_route_returns_404_for_unknown_team(_team_route_client):
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/teams/unknown-team/championship-path")
    finally:
        _clear_overrides()
    assert resp.status_code == 404


def test_championship_path_refresh_uses_card_refresh_rate_limit_bucket():
    for method, path, expected in [
        ("GET", "/api/teams/49/championship-path", True),
        ("GET", "/api/teams/los-angeles-lakers/championship-path", True),
        ("POST", "/api/teams/49/championship-path", False),
        ("GET", "/api/teams/los-angeles-lakers", False),
    ]:
        req = Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""})
        assert limits._is_fresh_feed_price_read(req) is expected
