"""#10090: the team page re-reads its on-screen rows by outcome id.

`/api/feed/price-cards` serves a market's `top_outcomes` only, and a team's leg
of a 30-way field is rarely among them; the team page itself took 2.7-5.8 s to
read (Nov 9). `/api/feed/outcome-prices` returns each named leg's row fields —
the fields `_query_team_futures` serves — refused where that read refuses them,
with an explicit disposition instead of a bare number.
"""
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.routes import feed_prices as route
from app.routes import user as user_routes
from app.utils import rate_limit

STAMP = datetime(2025, 6, 15, 18, 30, 12, 345678)  # naive, as the column stores it


def outcome(oid, mid, p=0.905, change=0.012, rank=2, winner=None, stamp=STAMP):
    return SimpleNamespace(id=oid, market_id=mid, current_probability=p, probability_change_24h=change,
                           rank=rank, is_winner=winner, last_updated=stamp)


def market(mid, outcomes, status="open", event_id=None):
    return SimpleNamespace(id=mid, status=status, event_id=event_id, outcomes=outcomes)


def scalars(rows):
    value = MagicMock()
    value.scalars.return_value.all.return_value = rows
    return value


def fake_db(outcomes, markets):
    db = AsyncMock()
    db.execute.side_effect = [scalars(outcomes), scalars(markets)]
    savepoint = AsyncMock()
    db.begin_nested = AsyncMock(return_value=savepoint)
    return db, savepoint


@pytest.fixture
def screen(monkeypatch):
    from app.routes import futures, prop_families
    state = {"withheld": {}, "stopped": {}, "raise": False}

    async def withheld(_db, markets):
        if state["raise"]:
            raise RuntimeError("screen down")
        return {m.id: set(state["withheld"].get(m.id, ())) for m in markets if m.id in state["withheld"]}

    async def stopped(_db, m):
        return set(state["stopped"].get(m.id, ()))

    monkeypatch.setattr(futures, "withheld_price_outcome_ids_for_markets", withheld)
    monkeypatch.setattr(prop_families, "_board_staleness_withheld", stopped)
    return state


@pytest.mark.asyncio
async def test_a_priced_leg_returns_the_team_row_fields(screen):
    lakers = outcome(261567710, 65677957, p=0.905, change=0.012, rank=2, winner=None)
    field = [lakers] + [outcome(261567700 + i, 65677957, p=0.5) for i in range(29)]
    db, _ = fake_db([lakers], [market(65677957, field)])
    items, dispositions = await user_routes._team_outcome_prices(db, [261567710])
    assert dispositions == {"outcome-261567710": "updated"}
    assert items == [{
        "outcome_id": 261567710, "market_id": 65677957, "probability": 0.905,
        "probability_change_24h": 0.012, "rank": 2, "total_outcomes": 30, "is_winner": False,
        "price_revision_at": "2025-06-15T18:30:12.345678+00:00",
    }]


@pytest.mark.asyncio
async def test_a_null_price_stays_null_never_zero(screen):
    leg = outcome(1, 9, p=None, change=None)
    db, _ = fake_db([leg], [market(9, [leg])])
    items, _ = await user_routes._team_outcome_prices(db, [1])
    assert items[0]["probability"] is None and items[0]["probability_change_24h"] is None


@pytest.mark.asyncio
async def test_every_refusal_is_explicit_and_carries_no_number(screen):
    priced = outcome(1, 10)
    screened = outcome(2, 20)
    stale = outcome(3, 30)
    closed = outcome(4, 40)
    game = outcome(5, 50)
    screen["withheld"] = {20: {2}}
    screen["stopped"] = {30: {3}}
    db, _ = fake_db(
        [priced, screened, stale, closed, game],
        [market(10, [priced]), market(20, [screened]), market(30, [stale]),
         market(40, [closed], status="closed"), market(50, [game], event_id=15344868)],
    )
    items, dispositions = await user_routes._team_outcome_prices(db, [1, 2, 3, 4, 5, 6])
    assert [i["outcome_id"] for i in items] == [1]
    assert dispositions == {
        "outcome-1": "updated", "outcome-2": "withheld", "outcome-3": "withheld",
        "outcome-4": "closed", "outcome-5": "closed", "outcome-6": "missing",
    }


@pytest.mark.asyncio
async def test_a_screen_that_cannot_run_patches_nothing(screen):
    screen["raise"] = True
    leg = outcome(1, 10)
    db, savepoint = fake_db([leg], [market(10, [leg])])
    items, dispositions = await user_routes._team_outcome_prices(db, [1])
    assert items == []
    assert dispositions == {"outcome-1": "unresolved"}
    savepoint.rollback.assert_awaited_once()


def test_the_live_read_and_the_page_read_share_the_same_refusals():
    page = inspect.getsource(user_routes._query_team_futures)
    live = inspect.getsource(user_routes._team_outcome_prices)
    for helper in ("withheld_price_outcome_ids_for_markets", "_board_staleness_withheld"):
        assert helper in page and helper in live, helper
    # The page read's base filters: open and not game-bound.
    assert 'FuturesMarket.status == "open"' in page and "FuturesMarket.event_id.is_(None)" in page
    assert 'market.status != "open"' in live and "market.event_id is not None" in live


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["", "0", "1,x", ",".join(["1"] * 51)])
async def test_bad_or_unbounded_ids_are_refused_before_the_database(raw):
    db = AsyncMock()
    with pytest.raises(HTTPException):
        await route.get_outcome_prices(Response(), raw, db)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_endpoint_keeps_request_order_and_is_never_cached(monkeypatch):
    monkeypatch.setattr(user_routes, "_team_outcome_prices", AsyncMock(return_value=(
        [{"outcome_id": 2}, {"outcome_id": 1}], {"outcome-1": "updated", "outcome-2": "updated", "outcome-3": "withheld"})))
    response = Response()
    body = await route.get_outcome_prices(response, "1,2,3,1", AsyncMock())
    assert [i["outcome_id"] for i in body["items"]] == [1, 2]
    assert body["dispositions"]["outcome-3"] == "withheld"
    assert response.headers["cache-control"] == "no-store"
    assert isinstance(body["built_at"], float)


def test_it_spends_the_card_refresh_budget_not_the_ordinary_one():
    def request(path):
        return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})
    assert rate_limit._is_fresh_feed_price_read(request("/api/feed/outcome-prices"))
    assert rate_limit._is_fresh_feed_price_read(request("/api/feed/price-cards"))
    assert not rate_limit._is_fresh_feed_price_read(request("/api/feed"))
