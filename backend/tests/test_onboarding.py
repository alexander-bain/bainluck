"""Tests for onboarding-related utilities in user.py.

Tests cover:
- Metro alias expansion
- Sport affinity expansion and compression
- Data structures and validation
"""

import pytest
from app.routes.user import (
    _expand_location_query,
    _expand_sport_affinities,
    _compress_sport_affinities,
    METRO_ALIASES,
    SPORT_AFFINITY_MAPPING,
    SPORT_KEY_TO_CATEGORY,
)


# =============================================================================
# Metro Alias Expansion Tests
# =============================================================================


class TestMetroAliasExpansion:
    """Tests for _expand_location_query()."""

    def test_direct_match(self):
        """A query that matches a key should include all its aliases."""
        terms = _expand_location_query("Boston")
        assert "boston" in terms
        assert "new england" in terms
        assert "foxborough" in terms

    def test_reverse_match(self):
        """A query that appears as a value should include the parent key."""
        terms = _expand_location_query("New England")
        assert "new england" in terms
        assert "boston" in terms
        assert "foxborough" in terms

    def test_case_insensitive(self):
        """Queries should be matched case-insensitively."""
        terms_upper = _expand_location_query("BOSTON")
        terms_lower = _expand_location_query("boston")
        assert set(terms_upper) == set(terms_lower)

    def test_unknown_location(self):
        """An unknown location should just return itself."""
        terms = _expand_location_query("Timbuktu")
        assert terms == ["timbuktu"]

    def test_golden_state_bay_area(self):
        """Golden State should expand to Bay Area metro."""
        terms = _expand_location_query("Golden State")
        assert "golden state" in terms
        assert "san francisco" in terms
        assert "bay area" in terms
        assert "oakland" in terms

    def test_bay_area_reverse(self):
        """Bay Area should also include Golden State."""
        terms = _expand_location_query("Bay Area")
        assert "bay area" in terms
        assert "golden state" in terms
        assert "san francisco" in terms

    def test_dc_washington(self):
        """DC and Washington should be aliased."""
        dc_terms = _expand_location_query("DC")
        assert "washington" in dc_terms
        assert "d.c." in dc_terms

        wa_terms = _expand_location_query("Washington")
        assert "dc" in wa_terms

    def test_philly_philadelphia(self):
        """Philly should expand to Philadelphia."""
        terms = _expand_location_query("Philly")
        assert "philadelphia" in terms

        terms = _expand_location_query("Philadelphia")
        assert "philly" in terms

    def test_los_angeles(self):
        """LA should expand to Los Angeles area."""
        terms = _expand_location_query("LA")
        assert "los angeles" in terms
        assert "anaheim" in terms
        assert "inglewood" in terms

    def test_whitespace_handling(self):
        """Leading/trailing whitespace should be trimmed."""
        terms = _expand_location_query("  Boston  ")
        assert "boston" in terms
        assert "new england" in terms

    def test_short_query(self):
        """Short query should still work."""
        terms = _expand_location_query("LA")
        assert "la" in terms
        assert "los angeles" in terms


# =============================================================================
# Sport Affinity Expansion Tests
# =============================================================================


class TestSportAffinityExpansion:
    """Tests for _expand_sport_affinities()."""

    def test_basic_expansion(self):
        """Football should expand to NFL and NCAAF."""
        result = _expand_sport_affinities({"football": 1.0})
        assert "americanfootball_nfl" in result
        assert "americanfootball_ncaaf" in result
        assert result["americanfootball_nfl"] == 1.0
        assert result["americanfootball_ncaaf"] == 1.0

    def test_basketball_expansion(self):
        """Basketball should expand to NBA, NCAAB, WNCAAB."""
        result = _expand_sport_affinities({"basketball": 0.3})
        assert "basketball_nba" in result
        assert "basketball_ncaab" in result
        assert "basketball_wncaab" in result
        assert all(v == 0.3 for v in result.values())

    def test_multiple_sports(self):
        """Multiple sports should all expand correctly."""
        result = _expand_sport_affinities({
            "football": 1.0,
            "hockey": 0.3,
        })
        assert result["americanfootball_nfl"] == 1.0
        assert result["americanfootball_ncaaf"] == 1.0
        assert result["icehockey_nhl"] == 0.3

    def test_unknown_sport_passthrough(self):
        """Unknown sport keys should pass through as-is."""
        result = _expand_sport_affinities({"curling": 0.5})
        assert result == {"curling": 0.5}

    def test_empty_input(self):
        """Empty input should return empty dict."""
        assert _expand_sport_affinities({}) == {}

    def test_zero_value_included(self):
        """Zero-value sports should still expand."""
        result = _expand_sport_affinities({"baseball": 0.0})
        assert "baseball_mlb" in result
        assert result["baseball_mlb"] == 0.0


# =============================================================================
# Sport Affinity Compression Tests
# =============================================================================


class TestSportAffinityCompression:
    """Tests for _compress_sport_affinities()."""

    def test_basic_compression(self):
        """Backend keys should compress to frontend categories."""
        result = _compress_sport_affinities({
            "americanfootball_nfl": 1.0,
            "americanfootball_ncaaf": 1.0,
        })
        assert result == {"football": 1.0}

    def test_max_value_wins(self):
        """When multiple keys map to same category, max value wins."""
        result = _compress_sport_affinities({
            "basketball_nba": 1.0,
            "basketball_ncaab": 0.3,
            "basketball_wncaab": 0.1,
        })
        assert result == {"basketball": 1.0}

    def test_multiple_categories(self):
        """Multiple categories should compress independently."""
        result = _compress_sport_affinities({
            "americanfootball_nfl": 1.0,
            "basketball_nba": 0.3,
            "icehockey_nhl": 0.1,
        })
        assert result == {"football": 1.0, "basketball": 0.3, "hockey": 0.1}

    def test_unknown_keys_skipped(self):
        """Unknown backend keys should be skipped in compression."""
        result = _compress_sport_affinities({
            "americanfootball_nfl": 1.0,
            "unknown_sport_xyz": 0.5,
        })
        assert result == {"football": 1.0}
        assert "unknown_sport_xyz" not in result

    def test_empty_input(self):
        """Empty input should return empty dict."""
        assert _compress_sport_affinities({}) == {}

    def test_roundtrip(self):
        """Expand then compress should return the original values."""
        original = {"football": 1.0, "basketball": 0.3, "hockey": 0.1}
        expanded = _expand_sport_affinities(original)
        compressed = _compress_sport_affinities(expanded)
        assert compressed == original


# =============================================================================
# Reverse Mapping Tests
# =============================================================================


class TestReverseMapping:
    """Tests for SPORT_KEY_TO_CATEGORY reverse mapping."""

    def test_all_expansion_keys_mapped(self):
        """Every key in SPORT_AFFINITY_MAPPING should have a reverse mapping."""
        for category, keys in SPORT_AFFINITY_MAPPING.items():
            for key in keys:
                assert key in SPORT_KEY_TO_CATEGORY, (
                    f"Missing reverse mapping for {key}"
                )
                assert SPORT_KEY_TO_CATEGORY[key] == category

    def test_nfl_maps_to_football(self):
        assert SPORT_KEY_TO_CATEGORY["americanfootball_nfl"] == "football"

    def test_nba_maps_to_basketball(self):
        assert SPORT_KEY_TO_CATEGORY["basketball_nba"] == "basketball"

    def test_nhl_maps_to_hockey(self):
        assert SPORT_KEY_TO_CATEGORY["icehockey_nhl"] == "hockey"

    def test_mlb_maps_to_baseball(self):
        assert SPORT_KEY_TO_CATEGORY["baseball_mlb"] == "baseball"


# =============================================================================
# Metro Aliases Consistency Tests
# =============================================================================


class TestMetroAliasesConsistency:
    """Verify the METRO_ALIASES dict is well-formed."""

    def test_all_values_are_lists(self):
        """All values should be lists of strings."""
        for key, values in METRO_ALIASES.items():
            assert isinstance(values, list), f"Value for '{key}' is not a list"
            for v in values:
                assert isinstance(v, str), f"Value '{v}' for key '{key}' is not a string"

    def test_no_empty_values(self):
        """No key should have an empty alias list."""
        for key, values in METRO_ALIASES.items():
            assert len(values) > 0, f"Key '{key}' has empty alias list"

    def test_keys_are_lowercase(self):
        """All keys should be lowercase."""
        for key in METRO_ALIASES:
            assert key == key.lower(), f"Key '{key}' is not lowercase"
