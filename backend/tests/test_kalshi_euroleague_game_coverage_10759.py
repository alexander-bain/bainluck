"""#10759: EuroLeague full-game winner quotes reach the ingest path."""

import asyncio
import time

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks.kalshi import _is_kalshi_game_ticker
from app.utils.prediction_market_matching import (
    extract_matchup_with_ticker_fallback,
    feeds_win_prob_blend,
)
from app.utils.sport_keys import get_sport_key_from_ticker, is_kalshi_game_level_ticker


@pytest.mark.asyncio
async def test_euroleague_winner_rescue_backfills_both_legs_despite_existing_game(monkeypatch):
    ticker = "KXEUROLEAGUEGAME-26OCT081200CZVDUB"
    title = "KK Crvena zvezda Belgrade vs Dubai Basketball"
    calls = []
    # Quotes are synthetic; labels and ticker are Root's exact provider contract.
    legs = [
        {
            "ticker": f"{ticker}-{code}",
            "event_ticker": ticker,
            "title": f"{name} wins",
            "yes_sub_title": name,
            "status": "active",
            "yes_bid_dollars": "0.4900",
            "yes_ask_dollars": "0.5100",
            "last_price_dollars": "0.5000",
            "close_time": "2026-10-10T16:00:00Z",
            "expected_expiration_time": "2026-10-08T19:00:00Z",
        }
        for code, name in [("DUB", "Dubai Basketball"),
                           ("CZV", "KK Crvena zvezda Belgrade")]
    ]
    client = KalshiAPIService()

    async def get_events(**kw):
        calls.append(kw)
        if kw.get("series_ticker") is None:
            # An existing game must not seal the current slate out of rescue.
            return [{"event_ticker": "KXEUROLEAGUEGAME-26OCT071200CZVDUB",
                     "title": title, "category": "Sports", "markets": legs}], None
        if kw["series_ticker"] == "KXEUROLEAGUEGAME":
            assert kw["with_nested_markets"] is False
            return [{"event_ticker": ticker, "title": title,
                     "category": "Sports", "mutually_exclusive": True,
                     "markets": []}], None
        return [], None

    async def get_markets(**kw):
        assert kw["series_ticker"] == "KXEUROLEAGUEGAME"
        return legs, None

    async def no_sleep(*args, **kwargs):
        pass

    monkeypatch.setattr(client, "get_events", get_events)
    monkeypatch.setattr(client, "get_markets", get_markets)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    events = await client._fetch_all_events_unfiltered(deadline=time.monotonic() + 1000)
    event = next(e for e in events if e.event_ticker == ticker)
    assert {m.ticker for m in event.markets} == {f"{ticker}-DUB", f"{ticker}-CZV"}
    assert any(c.get("series_ticker") == "KXEUROLEAGUEGAME" for c in calls)
    assert get_sport_key_from_ticker(ticker) == "basketball_euroleague"
    assert is_kalshi_game_level_ticker(ticker)
    assert _is_kalshi_game_ticker(ticker) == "EuroLeague"
    assert feeds_win_prob_blend(ticker)
    assert extract_matchup_with_ticker_fallback(title, ticker) is not None
    assert get_sport_key_from_ticker("KXEUROLEAGUETOTAL-26OCT081200CZVDUB") is None
