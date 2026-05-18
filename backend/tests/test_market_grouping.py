"""
Tests for market_grouping.py — threshold detection and canonical grouping.

Covers:
- extract_threshold: numeric threshold extraction from market/outcome names
- compute_threshold_stem: stem computation for grouping threshold variants
- compute_canonical_groups: grouping markets by canonical_market_key
- detect_threshold_groups: detecting threshold variants among outcomes
- discover_group_id_for_market: group_id computation for markets
"""

import pytest

from app.utils.market_grouping import (
    extract_threshold,
    compute_threshold_stem,
    compute_canonical_groups,
    detect_threshold_groups,
    detect_stat_prop_groups,
    detect_playoff_progression_groups,
    detect_all_groups,
    discover_group_id_for_market,
)


# ── extract_threshold ──


class TestExtractThreshold:
    """Tests for numeric threshold extraction from names."""

    def test_exceed_dollar_amount(self):
        result = extract_threshold("Will Bitcoin exceed $80,000?")
        assert result is not None
        value, unit, direction = result
        assert value == 80000.0
        assert "$" in unit
        assert direction == "above"

    def test_above_temperature(self):
        result = extract_threshold("Will the high be above 33°F?")
        assert result is not None
        value, unit, direction = result
        assert value == 33.0
        assert "°F" in unit
        assert direction == "above"

    def test_below_temperature(self):
        result = extract_threshold("Temperature below 20°C tomorrow?")
        assert result is not None
        value, unit, direction = result
        assert value == 20.0
        assert "°C" in unit
        assert direction == "below"

    def test_over_points(self):
        result = extract_threshold("Over 218.5 points")
        assert result is not None
        value, unit, direction = result
        assert value == 218.5
        assert "points" in unit
        assert direction == "above"

    def test_under_goals(self):
        result = extract_threshold("Under 2.5 goals")
        assert result is not None
        value, unit, direction = result
        assert value == 2.5
        assert "goal" in unit
        assert direction == "below"

    def test_at_least(self):
        result = extract_threshold("At least 250 yards")
        assert result is not None
        value, unit, direction = result
        assert value == 250.0
        assert direction == "above"

    def test_reach_million(self):
        result = extract_threshold("Will S&P 500 reach 6,500?")
        assert result is not None
        value, unit, direction = result
        assert value == 6500.0
        assert direction == "above"

    def test_simple_or_more(self):
        result = extract_threshold("33°F or more")
        assert result is not None
        value, unit, direction = result
        assert value == 33.0
        assert direction == "above"

    def test_simple_or_below(self):
        result = extract_threshold("33°F or below")
        assert result is not None
        value, unit, direction = result
        assert value == 33.0
        assert direction == "below"

    def test_no_threshold_team_name(self):
        """Team names and normal text should not match."""
        assert extract_threshold("Boston Celtics") is None

    def test_no_threshold_championship(self):
        assert extract_threshold("NBA Championship Winner 2025-26") is None

    def test_no_threshold_empty(self):
        assert extract_threshold("") is None

    def test_no_threshold_none(self):
        assert extract_threshold(None) is None


# ── compute_threshold_stem ──


class TestComputeThresholdStem:
    """Tests for threshold stem computation."""

    def test_bitcoin_stem_consistency(self):
        """Different dollar thresholds should produce the same stem."""
        stem_80k = compute_threshold_stem("Will Bitcoin exceed $80,000?")
        stem_90k = compute_threshold_stem("Will Bitcoin exceed $90,000?")
        stem_100k = compute_threshold_stem("Will Bitcoin exceed $100,000?")
        assert stem_80k is not None
        assert stem_80k == stem_90k == stem_100k

    def test_temperature_stem_consistency(self):
        """Different temperature thresholds should produce the same stem."""
        stem_33 = compute_threshold_stem("High temperature above 33°F?")
        stem_40 = compute_threshold_stem("High temperature above 40°F?")
        assert stem_33 is not None
        assert stem_33 == stem_40

    def test_points_stem_consistency(self):
        """Different point thresholds should produce the same stem."""
        stem_a = compute_threshold_stem("Over 218.5 points")
        stem_b = compute_threshold_stem("Over 225.5 points")
        assert stem_a is not None
        assert stem_a == stem_b

    def test_no_stem_for_non_threshold(self):
        """Non-threshold names should return None."""
        assert compute_threshold_stem("Boston Celtics") is None
        assert compute_threshold_stem("NBA Championship") is None

    def test_no_stem_empty(self):
        assert compute_threshold_stem("") is None
        assert compute_threshold_stem(None) is None


# ── compute_canonical_groups ──


class TestComputeCanonicalGroups:
    """Tests for canonical key grouping."""

    def test_groups_matching_keys(self):
        """Markets with the same canonical key should be grouped."""
        markets = [
            {"id": 1, "canonical_market_key": "basketball:NBA:championship:2025-26", "source": "polymarket"},
            {"id": 2, "canonical_market_key": "basketball:NBA:championship:2025-26", "source": "kalshi"},
            {"id": 3, "canonical_market_key": "basketball:NBA:mvp:2025-26", "source": "polymarket"},
        ]
        groups = compute_canonical_groups(markets)
        assert "basketball:NBA:championship:2025-26" in groups
        assert len(groups["basketball:NBA:championship:2025-26"]) == 2
        # MVP only has 1 market, so it shouldn't be in groups
        assert "basketball:NBA:mvp:2025-26" not in groups

    def test_no_groups_for_unique_keys(self):
        """Markets with unique keys should not form groups."""
        markets = [
            {"id": 1, "canonical_market_key": "basketball:NBA:championship:2025-26", "source": "polymarket"},
            {"id": 2, "canonical_market_key": "football:NFL:championship:2025-26", "source": "kalshi"},
        ]
        groups = compute_canonical_groups(markets)
        assert len(groups) == 0

    def test_skips_none_keys(self):
        """Markets without canonical keys should be skipped."""
        markets = [
            {"id": 1, "canonical_market_key": None, "source": "polymarket"},
            {"id": 2, "canonical_market_key": None, "source": "kalshi"},
        ]
        groups = compute_canonical_groups(markets)
        assert len(groups) == 0

    def test_same_source_siblings(self):
        """Markets from the same source with the same key should also group."""
        markets = [
            {"id": 1, "canonical_market_key": "politics::president:2028", "source": "polymarket"},
            {"id": 2, "canonical_market_key": "politics::president:2028", "source": "polymarket"},
        ]
        groups = compute_canonical_groups(markets)
        assert "politics::president:2028" in groups

    def test_preserves_duplicate_like_rows_for_caller_to_resolve(self):
        """Grouping should not silently drop duplicate-looking market rows."""
        markets = [
            {"id": 1, "canonical_market_key": "awards:oscars:best-picture:2026", "source": "polymarket"},
            {"id": 1, "canonical_market_key": "awards:oscars:best-picture:2026", "source": "polymarket"},
            {"id": 2, "canonical_market_key": "awards:oscars:best-picture:2026", "source": "kalshi"},
        ]

        groups = compute_canonical_groups(markets)

        grouped_ids = [m["id"] for m in groups["awards:oscars:best-picture:2026"]]
        assert grouped_ids == [1, 1, 2]

    def test_empty_input(self):
        assert compute_canonical_groups([]) == {}


# ── detect_threshold_groups ──


class TestDetectThresholdGroups:
    """Tests for threshold variant detection."""

    def test_bitcoin_threshold_group(self):
        """Bitcoin price threshold outcomes should form a group."""
        outcomes = [
            {"id": 1, "name": "Will Bitcoin exceed $80,000?", "market_id": 100},
            {"id": 2, "name": "Will Bitcoin exceed $90,000?", "market_id": 101},
            {"id": 3, "name": "Will Bitcoin exceed $100,000?", "market_id": 102},
        ]
        groups = detect_threshold_groups(outcomes)
        assert len(groups) == 1
        stem = list(groups.keys())[0]
        group = groups[stem]
        assert len(group) == 3
        # Should be sorted by threshold value
        assert group[0]["threshold_value"] == 80000.0
        assert group[1]["threshold_value"] == 90000.0
        assert group[2]["threshold_value"] == 100000.0

    def test_temperature_threshold_group(self):
        """Temperature threshold outcomes should form a group."""
        outcomes = [
            {"id": 1, "name": "33°F or below", "market_id": 200},
            {"id": 2, "name": "40°F or below", "market_id": 200},
            {"id": 3, "name": "50°F or below", "market_id": 200},
        ]
        groups = detect_threshold_groups(outcomes)
        assert len(groups) == 1
        group = list(groups.values())[0]
        assert len(group) == 3
        assert group[0]["threshold_value"] == 33.0
        assert group[2]["threshold_value"] == 50.0

    def test_no_group_for_single_threshold(self):
        """A single threshold outcome should not form a group."""
        outcomes = [
            {"id": 1, "name": "Will Bitcoin exceed $80,000?", "market_id": 100},
            {"id": 2, "name": "Boston Celtics", "market_id": 101},
        ]
        groups = detect_threshold_groups(outcomes)
        assert len(groups) == 0

    def test_no_group_for_non_threshold(self):
        """Non-threshold outcomes should not form groups."""
        outcomes = [
            {"id": 1, "name": "Boston Celtics", "market_id": 100},
            {"id": 2, "name": "Los Angeles Lakers", "market_id": 100},
        ]
        groups = detect_threshold_groups(outcomes)
        assert len(groups) == 0

    def test_empty_input(self):
        assert detect_threshold_groups([]) == {}

    def test_enriches_with_threshold_data(self):
        """Grouped outcomes should be enriched with threshold metadata."""
        outcomes = [
            {"id": 1, "name": "Over 218.5 points", "market_id": 100},
            {"id": 2, "name": "Over 225.5 points", "market_id": 101},
        ]
        groups = detect_threshold_groups(outcomes)
        assert len(groups) == 1
        group = list(groups.values())[0]
        assert group[0]["threshold_value"] == 218.5
        assert group[0]["threshold_direction"] == "above"
        assert "points" in group[0]["threshold_unit"]


# ── higher-level group detection ──


class TestHigherLevelGroupDetection:
    """Tests for grouped futures market detection helpers."""

    def test_stat_prop_markets_group_by_player_and_stat(self):
        markets = [
            {"id": 1, "name": "Jayson Tatum: 25+ Points"},
            {"id": 2, "name": "Jayson Tatum: 30+ Points"},
            {"id": 3, "name": "Jayson Tatum: 10+ Rebounds"},
        ]

        groups = detect_stat_prop_groups(markets)

        points_group = groups["stat_prop:jayson tatum:points"]
        assert [m["id"] for m in points_group] == [1, 2]
        assert [m["threshold_value"] for m in points_group] == [25.0, 30.0]
        assert "stat_prop:jayson tatum:rebounds" not in groups

    def test_playoff_progression_markets_group_by_team(self):
        markets = [
            {"id": 1, "name": "Lakers: Make Playoffs"},
            {"id": 2, "name": "Lakers: Make Round 2"},
            {"id": 3, "name": "Celtics: Win Championship"},
        ]

        groups = detect_playoff_progression_groups(markets)

        lakers_group = groups["playoff_progression:lakers"]
        assert [m["id"] for m in lakers_group] == [1, 2]
        assert [m["stage_order"] for m in lakers_group] == [1, 3]
        assert "playoff_progression:celtics" not in groups

    def test_detect_all_groups_ignores_placeholder_shaped_markets(self):
        markets = [
            {
                "id": 1,
                "name": "Player B",
                "outcomes": [{"id": 10, "name": "Player B"}],
            },
            {
                "id": 2,
                "name": "Player S",
                "outcomes": [{"id": 20, "name": "Player S"}],
            },
            {
                "id": 3,
                "name": "Jayson Tatum: 25+ Points",
                "outcomes": [{"id": 30, "name": "Over 25.5 points"}],
            },
            {
                "id": 4,
                "name": "Jayson Tatum: 30+ Points",
                "outcomes": [{"id": 40, "name": "Over 30.5 points"}],
            },
        ]

        groups = detect_all_groups(markets)

        assert groups["threshold"] == {
            "over #": [
                {
                    "id": 30,
                    "name": "Over 25.5 points",
                    "market_id": 3,
                    "threshold_value": 25.5,
                    "threshold_unit": "points",
                    "threshold_direction": "above",
                },
                {
                    "id": 40,
                    "name": "Over 30.5 points",
                    "market_id": 4,
                    "threshold_value": 30.5,
                    "threshold_unit": "points",
                    "threshold_direction": "above",
                },
            ]
        }
        assert [m["id"] for m in groups["stat_prop"]["stat_prop:jayson tatum:points"]] == [3, 4]
        assert groups["playoff_progression"] == {}


# ── discover_group_id_for_market ──


class TestDiscoverGroupId:
    """Tests for group_id discovery."""

    def test_polymarket_source(self):
        result = discover_group_id_for_market(
            source="polymarket",
            external_id="evt_123",
            canonical_market_key=None,
            name="NBA Championship",
            market_id=1,
        )
        assert result == ("polymarket:evt_123", "polymarket_event")

    def test_kalshi_source(self):
        result = discover_group_id_for_market(
            source="kalshi",
            external_id="KXNBACHAMP",
            canonical_market_key=None,
            name="NBA Championship",
            market_id=2,
        )
        assert result == ("kalshi:KXNBACHAMP", "kalshi_event")

    def test_canonical_key_fallback(self):
        result = discover_group_id_for_market(
            source="odds_api",
            external_id="12345",
            canonical_market_key="basketball:NBA:championship:2025-26",
            name="NBA Championship Winner 2025-26",
            market_id=3,
        )
        assert result == ("canonical:basketball:NBA:championship:2025-26", "canonical")

    def test_source_specific_group_id_takes_precedence_over_canonical_key(self):
        result = discover_group_id_for_market(
            source="polymarket",
            external_id="pm_event_456",
            canonical_market_key="basketball:NBA:championship:2025-26",
            name="NBA Championship Winner 2025-26",
            market_id=5,
        )
        assert result == ("polymarket:pm_event_456", "polymarket_event")

    def test_polymarket_without_external_id_falls_back_to_canonical_key(self):
        result = discover_group_id_for_market(
            source="polymarket",
            external_id=None,
            canonical_market_key="politics:us:president:2028",
            name="Who will win the 2028 US presidential election?",
            market_id=6,
        )
        assert result == ("canonical:politics:us:president:2028", "canonical")

    def test_no_group_for_unknown(self):
        result = discover_group_id_for_market(
            source="odds_api",
            external_id="12345",
            canonical_market_key=None,
            name="Some random market",
            market_id=4,
        )
        assert result is None
