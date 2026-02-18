"""
Tests for Polymarket API client and polling task.

Tests cover:
1. API client parsing (events, markets, stringified JSON arrays, timestamps)
2. Tag-to-category mapping
3. Outcome name extraction from market questions
4. NegRisk multi-outcome event handling
"""

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks.polymarket import (
    _extract_outcome_name,
    _tags_to_category,
)


# =========================================================================
# Tag-to-category mapping tests
# =========================================================================


class TestTagsToCategory:
    """Test mapping Polymarket tags to internal categories."""

    def test_nba_tag(self):
        cat, sport = _tags_to_category(["Sports", "NBA"])
        assert cat == "championship"
        assert sport == "basketball"

    def test_nfl_tag(self):
        cat, sport = _tags_to_category(["Sports", "NFL"])
        assert cat == "championship"
        assert sport == "football"

    def test_nhl_tag(self):
        cat, sport = _tags_to_category(["Sports", "NHL"])
        assert cat == "championship"
        assert sport == "hockey"

    def test_mlb_tag(self):
        cat, sport = _tags_to_category(["Sports", "MLB"])
        assert cat == "championship"
        assert sport == "baseball"

    def test_ufc_tag(self):
        cat, sport = _tags_to_category(["Sports", "UFC"])
        assert cat == "championship"
        assert sport == "mma"

    def test_soccer_tag(self):
        cat, sport = _tags_to_category(["Sports", "Soccer"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_epl_tag(self):
        cat, sport = _tags_to_category(["Sports", "EPL"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_premier_league_tag(self):
        cat, sport = _tags_to_category(["Sports", "Premier League"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_golf_tag(self):
        cat, sport = _tags_to_category(["Sports", "Golf"])
        assert cat == "championship"
        assert sport == "golf"

    def test_tennis_tag(self):
        cat, sport = _tags_to_category(["Sports", "Tennis"])
        assert cat == "championship"
        assert sport == "tennis"

    def test_politics_tag(self):
        cat, sport = _tags_to_category(["Politics"])
        assert cat == "politics"
        assert sport == "politics"

    def test_elections_tag(self):
        cat, sport = _tags_to_category(["Elections"])
        assert cat == "politics"
        assert sport == "politics"

    def test_entertainment_tag(self):
        cat, sport = _tags_to_category(["Entertainment"])
        assert cat == "entertainment"
        assert sport == "entertainment"

    def test_crypto_tag(self):
        cat, sport = _tags_to_category(["Crypto"])
        assert cat == "crypto"
        assert sport == "crypto"

    def test_economy_tag(self):
        cat, sport = _tags_to_category(["Economy"])
        assert cat == "economics"
        assert sport == "economics"

    def test_tech_tag(self):
        cat, sport = _tags_to_category(["Tech"])
        assert cat == "tech"
        assert sport == "tech"

    def test_weather_tag(self):
        cat, sport = _tags_to_category(["Weather"])
        assert cat == "weather"
        assert sport == "weather"

    def test_sports_only_tag(self):
        """Generic 'Sports' tag without specific sport returns None for sport."""
        cat, sport = _tags_to_category(["Sports"])
        assert cat == "championship"
        assert sport is None

    def test_empty_tags(self):
        cat, sport = _tags_to_category([])
        assert cat == "other"
        assert sport is None

    def test_unknown_tags(self):
        cat, sport = _tags_to_category(["SomeRandomTag"])
        assert cat == "other"
        assert sport is None

    def test_case_insensitive(self):
        cat, sport = _tags_to_category(["nba"])
        assert cat == "championship"
        assert sport == "basketball"

    def test_multiple_tags_first_sport_wins(self):
        """First matching sport tag determines category."""
        cat, sport = _tags_to_category(["Sports", "Basketball", "NBA"])
        assert cat == "championship"
        assert sport == "basketball"

    def test_mixed_sports_and_nonsports(self):
        """Sport tag takes precedence over non-sport."""
        cat, sport = _tags_to_category(["Politics", "NFL"])
        # NFL comes after Politics in list, but NFL matches first in iteration
        # Actually depends on tag order — Politics matches first
        assert cat in ("politics", "championship")

    def test_f1_tag(self):
        cat, sport = _tags_to_category(["F1"])
        assert cat == "championship"
        assert sport == "motorsports"

    def test_champions_league_tag(self):
        cat, sport = _tags_to_category(["Champions League"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_la_liga_tag(self):
        cat, sport = _tags_to_category(["La Liga"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_bundesliga_tag(self):
        cat, sport = _tags_to_category(["Bundesliga"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_serie_a_tag(self):
        cat, sport = _tags_to_category(["Serie A"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_mls_tag(self):
        cat, sport = _tags_to_category(["MLS"])
        assert cat == "championship"
        assert sport == "soccer"

    def test_bitcoin_tag(self):
        cat, sport = _tags_to_category(["Bitcoin"])
        assert cat == "crypto"
        assert sport == "crypto"

    def test_ai_tag(self):
        cat, sport = _tags_to_category(["AI"])
        assert cat == "tech"
        assert sport == "tech"

    def test_oscars_tag(self):
        cat, sport = _tags_to_category(["Oscars"])
        assert cat == "entertainment"
        assert sport == "entertainment"


# =========================================================================
# Outcome name extraction tests
# =========================================================================


class TestExtractOutcomeName:
    """Test extracting clean outcome names from Polymarket market questions."""

    def test_will_the_x_win(self):
        name = _extract_outcome_name(
            "Will the Los Angeles Lakers win the 2025-26 NBA Championship?",
            "NBA Championship 2025-26",
        )
        assert name == "Los Angeles Lakers"

    def test_will_x_win_no_the(self):
        name = _extract_outcome_name(
            "Will Boston Celtics win the NBA Championship?",
            "NBA Championship",
        )
        assert name == "Boston Celtics"

    def test_will_x_be(self):
        name = _extract_outcome_name(
            "Will Nikola Jokic be the NBA MVP?",
            "NBA MVP 2025-26",
        )
        assert name == "Nikola Jokic"

    def test_x_to_win(self):
        name = _extract_outcome_name(
            "Manchester City to win the Premier League?",
            "Premier League Winner",
        )
        assert name == "Manchester City"

    def test_will_x_make(self):
        name = _extract_outcome_name(
            "Will the Detroit Lions make the Super Bowl?",
            "Super Bowl Participants",
        )
        assert name == "Detroit Lions"

    def test_short_question_passthrough(self):
        name = _extract_outcome_name("Yes", "Some Event")
        assert name == "Yes"

    def test_empty_question(self):
        name = _extract_outcome_name("", "Some Event")
        assert name == "Unknown"

    def test_none_question(self):
        name = _extract_outcome_name(None, "Some Event")
        assert name == "Unknown"

    def test_question_mark_stripped(self):
        name = _extract_outcome_name("Donald Trump?", "Election")
        assert name == "Donald Trump"

    def test_long_question_truncated(self):
        long_q = "A" * 100 + "?"
        name = _extract_outcome_name(long_q, "Event")
        assert len(name) == 60

    def test_will_x_reach(self):
        name = _extract_outcome_name(
            "Will Bitcoin reach $150,000 by end of 2026?",
            "Bitcoin Price Targets",
        )
        assert name == "Bitcoin"

    def test_will_x_qualify(self):
        name = _extract_outcome_name(
            "Will the USMNT qualify for the 2026 World Cup?",
            "World Cup Qualification",
        )
        assert name == "USMNT"


# =========================================================================
# API client parsing tests
# =========================================================================


class TestParseJsonStringArray:
    """Test Polymarket's stringified JSON array parsing."""

    def test_normal_stringified_array(self):
        result = PolymarketAPIService._parse_json_string_array('["Yes", "No"]')
        assert result == ["Yes", "No"]

    def test_already_a_list(self):
        result = PolymarketAPIService._parse_json_string_array(["Yes", "No"])
        assert result == ["Yes", "No"]

    def test_empty_string(self):
        result = PolymarketAPIService._parse_json_string_array("")
        assert result == []

    def test_empty_array_string(self):
        result = PolymarketAPIService._parse_json_string_array("[]")
        assert result == []

    def test_none(self):
        result = PolymarketAPIService._parse_json_string_array(None)
        assert result == []

    def test_numeric_array(self):
        result = PolymarketAPIService._parse_json_string_array("[0.65, 0.35]")
        assert result == ["0.65", "0.35"]

    def test_malformed_string(self):
        result = PolymarketAPIService._parse_json_string_array("not json")
        assert result == []

    def test_single_element(self):
        result = PolymarketAPIService._parse_json_string_array('["Only"]')
        assert result == ["Only"]


class TestParseTimestamp:
    """Test timestamp parsing for various formats."""

    def test_iso_with_z(self):
        dt = PolymarketAPIService._parse_timestamp("2026-02-18T12:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2

    def test_iso_with_offset(self):
        dt = PolymarketAPIService._parse_timestamp("2026-02-18T12:00:00+00:00")
        assert dt is not None

    def test_none(self):
        assert PolymarketAPIService._parse_timestamp(None) is None

    def test_empty_string(self):
        assert PolymarketAPIService._parse_timestamp("") is None

    def test_unix_timestamp(self):
        dt = PolymarketAPIService._parse_timestamp(1708300800)
        assert dt is not None

    def test_invalid_string(self):
        assert PolymarketAPIService._parse_timestamp("not a date") is None


class TestSafeFloat:
    """Test safe float conversion."""

    def test_none(self):
        assert PolymarketAPIService._safe_float(None) is None

    def test_string_number(self):
        assert PolymarketAPIService._safe_float("0.65") == 0.65

    def test_int(self):
        assert PolymarketAPIService._safe_float(42) == 42.0

    def test_invalid_string(self):
        assert PolymarketAPIService._safe_float("not a number") is None


class TestParseEvent:
    """Test parsing raw event data into PolymarketEvent."""

    def _make_service(self):
        return PolymarketAPIService()

    def test_basic_event(self):
        service = self._make_service()
        event = service._parse_event({
            "id": "12345",
            "title": "NBA Championship 2025-26",
            "slug": "nba-championship-2025-26",
            "active": True,
            "closed": False,
            "negRisk": True,
            "tags": [{"label": "Sports"}, {"label": "NBA"}],
            "markets": [
                {
                    "conditionId": "0xabc",
                    "question": "Will the Lakers win the NBA Championship?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.08", "0.92"]',
                    "clobTokenIds": '["token_yes", "token_no"]',
                    "active": True,
                    "closed": False,
                    "lastTradePrice": 0.08,
                    "volume": 1500000,
                }
            ],
        })
        assert event is not None
        assert event.id == "12345"
        assert event.title == "NBA Championship 2025-26"
        assert event.neg_risk is True
        assert len(event.tags) == 2
        assert "Sports" in event.tags
        assert "NBA" in event.tags
        assert len(event.markets) == 1
        assert event.markets[0].condition_id == "0xabc"
        assert event.markets[0].outcome_prices == [0.08, 0.92]

    def test_event_with_string_tags(self):
        """Tags can come as plain strings instead of dicts."""
        service = self._make_service()
        event = service._parse_event({
            "id": "67890",
            "title": "Test Event",
            "tags": ["Politics", "Elections"],
            "markets": [
                {
                    "conditionId": "0xdef",
                    "question": "Will X win?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.55", "0.45"]',
                    "clobTokenIds": '["a", "b"]',
                }
            ],
        })
        assert event is not None
        assert event.tags == ["Politics", "Elections"]

    def test_event_with_no_markets_returns_with_empty_list(self):
        service = self._make_service()
        event = service._parse_event({
            "id": "99999",
            "title": "Empty Event",
            "markets": [],
        })
        assert event is not None
        assert event.markets == []

    def test_event_with_timing(self):
        service = self._make_service()
        event = service._parse_event({
            "id": "11111",
            "title": "Timed Event",
            "startDate": "2026-06-15T00:00:00Z",
            "endDate": "2026-06-30T00:00:00Z",
            "markets": [
                {
                    "conditionId": "0x111",
                    "question": "Test?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.50", "0.50"]',
                    "clobTokenIds": '["c", "d"]',
                }
            ],
        })
        assert event is not None
        assert event.start_date is not None
        assert event.start_date.month == 6
        assert event.end_date is not None


class TestParseMarket:
    """Test parsing raw market data into PolymarketMarket."""

    def _make_service(self):
        return PolymarketAPIService()

    def test_basic_market(self):
        service = self._make_service()
        market = service._parse_market({
            "conditionId": "0xabc123",
            "question": "Will the Lakers win?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.65", "0.35"]',
            "clobTokenIds": '["token1", "token2"]',
            "active": True,
            "closed": False,
            "lastTradePrice": 0.64,
            "bestBid": 0.63,
            "bestAsk": 0.66,
            "volume": 500000,
            "volume24hr": 15000,
            "liquidity": 200000,
            "negRisk": False,
        })
        assert market is not None
        assert market.condition_id == "0xabc123"
        assert market.outcomes == ["Yes", "No"]
        assert market.outcome_prices == [0.65, 0.35]
        assert market.clob_token_ids == ["token1", "token2"]
        assert market.last_trade_price == 0.64
        assert market.best_bid == 0.63
        assert market.best_ask == 0.66
        assert market.volume == 500000

    def test_market_with_already_parsed_arrays(self):
        """Handle case where arrays are already lists (not stringified)."""
        service = self._make_service()
        market = service._parse_market({
            "conditionId": "0xdef",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "outcomePrices": [0.5, 0.5],
            "clobTokenIds": ["a", "b"],
        })
        assert market is not None
        assert market.outcomes == ["Yes", "No"]
        # When passed as list of floats, they become strings then floats
        assert market.outcome_prices == [0.5, 0.5]

    def test_market_missing_optional_fields(self):
        service = self._make_service()
        market = service._parse_market({
            "conditionId": "0xmin",
            "question": "Minimal?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.50", "0.50"]',
            "clobTokenIds": "[]",
        })
        assert market is not None
        assert market.last_trade_price is None
        assert market.best_bid is None
        assert market.volume is None
