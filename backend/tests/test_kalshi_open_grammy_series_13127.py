"""Fetch and upsert active Grammy fields even when the main cursor is in history."""

import asyncio
import time

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks.kalshi import _floor_series_first


def _raw_event(ticker: str, name: str, status: str) -> dict:
    return {
        "event_ticker": ticker,
        "title": name,
        "category": "Entertainment",
        "markets": [
            {
                "ticker": f"{ticker}-A",
                "event_ticker": ticker,
                "title": name,
                "yes_sub_title": "One contender",
                "status": status,
                "yes_bid_dollars": "0.22",
                "yes_ask_dollars": "0.23",
            }
        ],
    }


@pytest.mark.asyncio
async def test_open_grammys_reach_the_writer_ahead_of_history(monkeypatch):
    history = _raw_event("KXGRAMMY-SOTY68", "Previous Song of the Year", "finalized")
    open_events = {
        "KXGRAMMY": _raw_event("KXGRAMMY-SOTY69", "Song of the Year", "active"),
        "KXGRAMAOTY": _raw_event("KXGRAMAOTY-69", "Album of the Year", "active"),
        "KXGRAMBNA": _raw_event("KXGRAMBNA-69", "Best New Artist", "active"),
    }
    calls = []

    async def fake_events(**options):
        series = options.get("series_ticker")
        if series is None:
            return [history], None
        calls.append((series, options["status"], options["with_nested_markets"]))
        if series in open_events and options["status"] == "open":
            return [open_events[series]], None
        return [], None

    async def fake_markets(**options):
        return [], None

    async def no_sleep(*args, **kwargs):
        pass

    client = KalshiAPIService()
    monkeypatch.setattr(client, "get_events", fake_events)
    monkeypatch.setattr(client, "get_markets", fake_markets)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    events = await client._fetch_all_events_unfiltered(deadline=time.monotonic() + 400)
    for series in open_events:
        assert (series, "open", True) in calls
        grammy_index = calls.index((series, "open", True))
        assert calls.index(("KXNFLGAME", None, False)) < grammy_index
        assert grammy_index < calls.index(("KXEUROLEAGUEGAME", None, False))

    ordered = _floor_series_first(events)
    assert {event.event_ticker for event in ordered[:-1]} == {
        row["event_ticker"] for row in open_events.values()
    }
    assert all(event.markets for event in ordered)
    assert ordered[-1].event_ticker == history["event_ticker"]
