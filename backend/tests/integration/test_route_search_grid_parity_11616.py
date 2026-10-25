"""Search and typeahead consume detail's cached elimination universe (#11616).

Real ASGI routes, synthetic same-input boards and existing grid fixture. SQL is
stubbed at the existing search integration seam; no production/grid build runs.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes import events, futures
from app.services.database import get_db, get_db_rw
from app.utils import grid_out_division_legs as grid
from tests.integration.test_route_search_linked_kickoff_8906 import _session
from tests.test_discover_division_card_reads_the_grid_out_verdict_11493 import _grid
from tests.test_search_detail_parity_11616 import STAMP, market


def _board(mid=11616):
    board = market([0.60, 0.60, 0.50])
    board.id = mid
    board.name = "MLB 2026: World Series Division Winner"
    board.canonical_market_key = "baseball:MLB:division_winner:2026"
    board.source = "polymarket"
    board.llm_sport_category = "baseball"
    board.category = "championship"
    board.market_tier = 4
    board.market_type = "field"
    board.sport_id = None
    board.volume = 900_000
    for outcome, name in zip(board.outcomes, ("NL Central", "AL East", "AL Central")):
        outcome.name = name
    return board


def _rows(value, mid):
    if isinstance(value, dict):
        if value.get("market_id", value.get("id")) == mid and "top_outcomes" in value:
            yield value["top_outcomes"]
        else:
            for child in value.values():
                yield from _rows(child, mid)
    elif isinstance(value, list):
        for child in value:
            yield from _rows(child, mid)


async def _request(monkeypatch, endpoint, boards):
    from app.main import app

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    session = _session(boards, [], [])

    async def db():
        yield session

    async def no_user():
        return None

    saved = app.dependency_overrides.copy()
    app.dependency_overrides.update({get_db: db, get_db_rw: db, get_optional_user: no_user})
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(f"/api/events/{endpoint}", params={"q": "division"})
                assert response.status_code == 200, response.text
                return response.json()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
@pytest.mark.parametrize("available", [True, False])
async def test_actual_routes_use_the_same_grid_universe(monkeypatch, endpoint, available):
    board = _board()
    cached = _grid() if available else None
    read = AsyncMock(return_value=cached)
    with patch.object(grid, "read_cached_grid", read):
        body = await _request(monkeypatch, endpoint, [board, _board(1161602)])
    # One cached payload for the whole pool, never a read per outcome/market.
    read.assert_awaited_once_with("mlb")
    expected = futures._format_market_detail(
        board, out_division_labels=grid.out_division_labels(cached, "2026")
    )
    expected_prices = {o["name"]: o["probability"] for o in expected["outcomes"]}
    rows = list(_rows(body, board.id))
    assert rows, body
    for selected in rows:
        assert selected
        assert {o["name"]: o["probability"] for o in selected} == expected_prices
        assert ("AL Central" not in expected_prices) is available
    if available:
        assert expected_prices == {"NL Central": 0.5, "AL East": 0.5}
    for card in body.get("futures", []):
        if card["id"] == board.id:
            assert card["outcome_count"] == len(expected_prices)


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_unrelated_boards_pay_no_grid_read(monkeypatch, endpoint):
    board = _board()
    board.canonical_market_key = None
    read = AsyncMock(return_value=_grid())
    with patch.object(grid, "read_cached_grid", read):
        body = await _request(monkeypatch, endpoint, [board])
    read.assert_not_awaited()
    assert list(_rows(body, board.id))


async def test_excluded_new_quote_does_not_make_eligible_siblings_stale():
    board = _board()
    for outcome in board.outcomes[:2]:
        outcome.last_updated = STAMP - timedelta(days=45)
    with patch.object(events, "_withheld_price_outcome_ids", AsyncMock(return_value=set())), patch.object(
        events, "_fleet_newest_observation", AsyncMock(return_value=None)
    ):
        refused = await events._search_withheld_price_ids(
            AsyncMock(), board, out_division_labels=frozenset({"al central"})
        )
    assert refused == set()
    selected = events._build_search_top_outcomes(
        board, withheld=refused, out_division_labels=frozenset({"al central"})
    )
    assert {o["name"]: o["probability"] for o in selected} == {
        "NL Central": 0.5, "AL East": 0.5,
    }
