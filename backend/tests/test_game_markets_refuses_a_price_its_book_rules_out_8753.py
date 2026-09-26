"""#8753 — `/api/events/{id}/game-markets` refuses a leg its own book prices out.

WHAT A READER SAW. ``/events/15315945`` (Northwestern @ Indiana, live) served
*First Team to Score a TD* in ``other[]`` as Indiana 0.96 / Northwestern 0.42 /
No TD 0.01 — 139% over three exclusive outcomes — with Indiana's 0.96 sitting
above its own stored 0.95 ask. ``book_refutes_price(0.59, 0.95, 0.96)`` is True,
and ``/futures/{id}`` already withholds that leg through #6532's arm; the game
page never asked. The writer half (the socket storing the trade) is pinned in
``test_kalshi_socket_prices_by_the_rest_rule_8753``; this file pins the reader.

Every route test runs the treatment beside its control: the SAME seed with only
the refuted leg's price moved inside its book, so a gate that emptied the card
for an unrelated reason cannot pass.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import _leg_price_refuted_by_its_book
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 15315945
MARKET_ID = 61817501
INDIANA, NORTHWESTERN, NO_TD = 1, 2, 3


def _leg(id, name, price, bid, ask):
    o = _make_outcome(id=id, market_id=MARKET_ID, name=name, probability=price)
    o.current_yes_bid = bid
    o.current_yes_ask = ask
    return o


def _specimen(indiana_price=0.96):
    event = _make_event(
        id=EVENT_ID,
        home_team="Indiana Hoosiers",
        away_team="Northwestern Wildcats",
        status="live",
        sport_key="americanfootball_ncaaf",
    )
    market = _make_futures_market(
        id=MARKET_ID,
        name="Northwestern vs Indiana: First Team to Score a TD",
        source="kalshi",
    )
    market.event_id = EVENT_ID
    market.status = "open"
    outcomes = [
        # The stored rows from the issue's evidence table, verbatim.
        _leg(INDIANA, "Indiana scores first TD", indiana_price, 0.59, 0.95),
        _leg(NORTHWESTERN, "Northwestern scores first TD", 0.42, 0.04, 0.46),
        _leg(NO_TD, "No team scores a TD", 0.01, 0.00, 0.01),
    ]
    return event, [market], outcomes


async def _served_legs(seed) -> dict[str, float]:
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, markets, outcomes = seed
    session = _make_event_detail_session(
        event=event, futures=markets, outcomes=outcomes
    )

    async def _db():
        yield session

    async def _user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{EVENT_ID}/game-markets")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()
    return {
        r["outcome_name"]: r["probability"]
        for r in payload["other"]
        if r.get("_market_id") == MARKET_ID
    }


@pytest.mark.asyncio
async def test_the_specimen_leg_above_its_own_ask_is_not_served():
    legs = await _served_legs(_specimen())

    assert "Indiana scores first TD" not in legs, (
        "the page still prints Indiana 96% above its own 95c ask — the card's "
        f"three exclusive legs sum to 139% (#8753): {legs}"
    )
    assert set(legs) == {"Northwestern scores first TD", "No team scores a TD"}, (
        "the refusal reached legs whose own book does not refute them — it must "
        f"take one leg, never the card: {legs}"
    )


@pytest.mark.asyncio
async def test_control_the_same_leg_priced_inside_its_book_is_served():
    # 0.77 is what the REST rule (and, after #8753, the socket) stores for a
    # 0.59/0.95 book. Only the gate's input moved, so only the gate can explain
    # the treatment above.
    legs = await _served_legs(_specimen(indiana_price=0.77))

    assert legs.get("Indiana scores first TD") == pytest.approx(0.77), (
        f"a price inside its own book was refused — the arm is over-firing: {legs}"
    )


# ------------------------------------------------------ the predicate's edges ----


def _row(price, bid, ask, *, source="kalshi", is_winner=None, resolution_source=None):
    market = MagicMock()
    market.source = source
    outcome = MagicMock()
    outcome.current_probability = price
    outcome.current_yes_bid = bid
    outcome.current_yes_ask = ask
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    return market, outcome


def test_production_decimals_are_read():
    assert _leg_price_refuted_by_its_book(
        *_row(Decimal("0.9600"), Decimal("0.5900"), Decimal("0.9500"))
    )


def test_a_graded_winner_keeps_its_price_whatever_the_book_says():
    # Settled means settled: the predicate's exemption, reached through the helper.
    assert not _leg_price_refuted_by_its_book(
        *_row(1.0, 0.59, 0.95, is_winner=True, resolution_source="kalshi_api")
    )


def test_a_polymarket_leg_is_not_asked_the_kalshi_rule():
    assert not _leg_price_refuted_by_its_book(
        *_row(0.96, 0.59, 0.95, source="polymarket")
    )


def test_an_unreadable_book_refutes_nothing():
    # An unset MagicMock column floats to 1.0; read as a bid it would refute every
    # price below 0.995. Not a number ⇒ no book ⇒ the leg stays priced.
    unset = MagicMock()
    assert float(unset) == 1.0  # the trap, stated
    assert not _leg_price_refuted_by_its_book(*_row(0.52, unset, unset))
    assert not _leg_price_refuted_by_its_book(*_row(0.52, None, None))
