"""#10090: a price card carries its live game's period and clock.

Search patches a live game's probability, score and clock together, or not at
all (Fable, Nov 8: "a card's probability must never be newer than its score").
`/api/feed/price-cards` already carries the score and the probability from one
row read; `live_state` adds the period and clock from the same row, normalised
the way `/api/events/search` serves them as `espn.period` / `espn.game_clock`.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import feed, feed_prices as route
from tests.test_feed_price_cards_9515 import NOW, event, result


def _live(value, *, sport="americanfootball_nfl", period="2nd Quarter", clock="4:12", home=14, away=10):
    value.status = "live"
    value.period = period
    value.game_clock = clock
    value.home_score = home
    value.away_score = away
    value.sport = SimpleNamespace(key=sport, name="NFL")
    return value


async def _cards(monkeypatch, value):
    db = AsyncMock()
    db.execute.return_value = result([value])
    monkeypatch.setattr(route, "folded_probability_sources_with_revision", AsyncMock(return_value=(
        {"kalshi": {"value": .64, "updated_at": NOW.isoformat()}}, {"1": 9})))
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    items, states = await route._event_cards(db, [1], NOW)
    return items, states


@pytest.mark.asyncio
async def test_live_card_carries_period_clock_score_and_probability_from_one_read(monkeypatch):
    items, states = await _cards(monkeypatch, _live(event()))
    assert states == {"event-1": "updated"}
    data = items[0]["data"]
    assert data["live_state"] == {"period": "2nd Quarter", "game_clock": "4:12"}
    assert (data["home_score"], data["away_score"]) == (14, 10)
    assert data["current_odds"]["home_probability"] == .64


@pytest.mark.asyncio
async def test_baseball_is_normalised_as_search_serves_it(monkeypatch):
    # `normalize_live_game_state`: baseball keeps the inning and drops ESPN's clock.
    items, _ = await _cards(monkeypatch, _live(event(), sport="baseball_mlb", period="Top 7th", clock="0:00"))
    state = items[0]["data"]["live_state"]
    assert state["game_clock"] is None
    assert state["period"] and "7" in state["period"]


@pytest.mark.asyncio
async def test_no_period_or_clock_is_null_not_absent(monkeypatch):
    value = _live(event(), period=None, clock=None)
    items, _ = await _cards(monkeypatch, value)
    assert items[0]["data"]["live_state"] == {"period": None, "game_clock": None}


def test_live_state_of_a_missing_row_is_none():
    assert route._live_state(None) is None
