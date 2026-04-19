"""Tests for Kalshi API service parsing methods.

Covers:
- _parse_market: dual price format (dollars vs cents), zero handling, volume FP
- _parse_event: event with/without nested markets
- _parse_timestamp: ISO format variants
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.kalshi_api import KalshiAPIService


@pytest.fixture
def client():
    return KalshiAPIService()


@pytest.fixture
def fixtures():
    path = Path(__file__).parent / "fixtures" / "kalshi_fixtures.json"
    with open(path) as f:
        return json.load(f)


# ── _parse_market ─────────────────────────────────────────────────────


class TestParseMarket:
    """Test the dual price format parsing in _parse_market."""

    def test_dollars_preferred_over_cents(self, client, fixtures):
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.yes_bid == 0.65
        assert market.yes_ask == 0.68
        assert market.no_bid == 0.32
        assert market.no_ask == 0.35
        assert market.last_price == 0.66

    def test_cents_fallback_when_no_dollars(self, client, fixtures):
        market = client._parse_market(fixtures["market_cents_only"])
        assert market is not None
        assert market.yes_bid == pytest.approx(0.72)
        assert market.yes_ask == pytest.approx(0.75)
        assert market.no_bid == pytest.approx(0.25)
        assert market.no_ask == pytest.approx(0.28)
        assert market.last_price == pytest.approx(0.73)

    def test_zero_dollar_bid_is_valid(self, client, fixtures):
        """$0.00 bid is valid data (no one bidding), not missing."""
        market = client._parse_market(fixtures["market_zero_dollar_bid"])
        assert market is not None
        assert market.yes_bid == 0.0
        assert market.yes_ask == 0.01
        assert market.no_bid == 0.99
        assert market.no_ask == 1.0

    def test_minimal_market(self, client, fixtures):
        market = client._parse_market(fixtures["market_minimal"])
        assert market is not None
        assert market.ticker == "KXMIN"
        assert market.status == "closed"
        assert market.yes_bid is None
        assert market.yes_ask is None
        assert market.last_price is None
        assert market.volume is None

    def test_settled_market_result(self, client, fixtures):
        market = client._parse_market(fixtures["market_settled"])
        assert market is not None
        assert market.result == "yes"
        assert market.last_price == 1.0
        assert market.volume == 99999

    def test_volume_fp_preferred(self, client, fixtures):
        """Volume FP string fields override integer fields."""
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.volume == 12345
        assert market.volume_24h == 678
        assert market.open_interest == 4500

    def test_volume_integer_fallback(self, client, fixtures):
        market = client._parse_market(fixtures["market_cents_only"])
        assert market is not None
        assert market.volume == 5000
        assert market.volume_24h == 200
        assert market.open_interest == 1500

    def test_basic_fields(self, client, fixtures):
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.ticker == "KXNBA-CELTICS-WIN-2026"
        assert market.event_ticker == "KXNBA-CELTICS-2026"
        assert market.title == "Will the Celtics win?"
        assert market.subtitle == "Game 7 Championship"
        assert market.yes_sub_title == "Celtics win"
        assert market.no_sub_title == "Celtics lose"
        assert market.status == "active"

    def test_timestamps_parsed(self, client, fixtures):
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.open_time is not None
        assert isinstance(market.open_time, datetime)
        assert market.close_time is not None
        assert market.expiration_time is not None

    def test_empty_dict(self, client):
        market = client._parse_market({})
        assert market is not None
        assert market.ticker == ""
        assert market.status == ""


# ── _parse_event ──────────────────────────────────────────────────────


class TestParseEvent:

    def test_event_with_markets(self, client, fixtures):
        event = client._parse_event(fixtures["event_with_markets"])
        assert event is not None
        assert event.event_ticker == "KXNBA-GAME1"
        assert event.title == "NBA Game 1"
        assert event.subtitle == "Eastern Conference Finals"
        assert event.category == "Sports"
        assert event.mutually_exclusive is True
        assert len(event.markets) == 2
        assert event.markets[0].ticker == "KXNBA-GAME1-WIN"
        assert event.markets[1].ticker == "KXNBA-GAME1-TOTAL"

    def test_event_empty_markets(self, client, fixtures):
        event = client._parse_event(fixtures["event_empty_markets"])
        assert event is not None
        assert event.event_ticker == "KXEMPTY-EVT"
        assert len(event.markets) == 0

    def test_event_no_subtitle(self, client, fixtures):
        event = client._parse_event(fixtures["event_no_subtitle"])
        assert event is not None
        assert event.subtitle is None
        assert event.category == "Politics"

    def test_event_missing_markets_key(self, client):
        event = client._parse_event({"event_ticker": "TEST", "title": "Test"})
        assert event is not None
        assert len(event.markets) == 0

    def test_event_defaults(self, client):
        event = client._parse_event({})
        assert event is not None
        assert event.event_ticker == ""
        assert event.title == ""
        assert event.mutually_exclusive is True


# ── _parse_timestamp ──────────────────────────────────────────────────


class TestParseTimestamp:

    def test_z_suffix(self, client):
        result = client._parse_timestamp("2026-04-10T15:00:00Z")
        assert result is not None
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 10

    def test_offset_format(self, client):
        result = client._parse_timestamp("2026-04-10T15:00:00+00:00")
        assert result is not None
        assert isinstance(result, datetime)

    def test_none_returns_none(self, client):
        assert client._parse_timestamp(None) is None

    def test_empty_string_returns_none(self, client):
        assert client._parse_timestamp("") is None

    def test_invalid_string_returns_none(self, client):
        assert client._parse_timestamp("not-a-date") is None

    def test_z_and_offset_produce_same_time(self, client):
        z = client._parse_timestamp("2026-04-10T15:00:00Z")
        offset = client._parse_timestamp("2026-04-10T15:00:00+00:00")
        assert z == offset
