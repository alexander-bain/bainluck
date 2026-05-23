"""Tests for onboarding-related utilities in user.py.

Tests cover:
- Metro alias expansion
- Sport affinity expansion and compression
- Data structures and validation
"""

from types import SimpleNamespace

import pytest
from app.models.models import UserPreference
from app.routes.user import (
    _expand_location_query,
    _expand_sport_affinities,
    _compress_sport_affinities,
    get_preferences,
    submit_onboarding,
    METRO_ALIASES,
    OnboardingRequest,
    SPORT_AFFINITY_MAPPING,
    SPORT_KEY_TO_CATEGORY,
)


class _FakeScalarResult:
    def __init__(self, value=None):
        self.value = value

    def all(self):
        return []

    def scalar_one_or_none(self):
        return self.value


class _FakeRowsResult:
    def all(self):
        return []


class _FakeOnboardingDb:
    def __init__(self):
        self.added = []
        self.preferences = None
        self.execute_count = 0
        self.flush_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        if self.execute_count in (2, 3):
            return _FakeScalarResult(self.preferences)
        return _FakeRowsResult()

    def add(self, item):
        self.added.append(item)
        if isinstance(item, UserPreference):
            self.preferences = item

    async def flush(self):
        self.flush_count += 1


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

    def test_legacy_football_expansion(self):
        """Legacy 'football' key should still expand to NFL and NCAAF."""
        result = _expand_sport_affinities({"football": 1.0})
        assert "americanfootball_nfl" in result
        assert "americanfootball_ncaaf" in result
        assert result["americanfootball_nfl"] == 1.0
        assert result["americanfootball_ncaaf"] == 1.0

    def test_split_nfl_expansion(self):
        """New 'nfl' key should expand to just NFL."""
        result = _expand_sport_affinities({"nfl": 1.0})
        assert "americanfootball_nfl" in result
        assert "americanfootball_ncaaf" not in result
        assert result["americanfootball_nfl"] == 1.0

    def test_split_college_football_expansion(self):
        """New 'college_football' key should expand to just NCAAF."""
        result = _expand_sport_affinities({"college_football": 0.3})
        assert "americanfootball_ncaaf" in result
        assert "americanfootball_nfl" not in result
        assert result["americanfootball_ncaaf"] == 0.3

    def test_split_nba_expansion(self):
        """New 'nba' key should expand to just NBA."""
        result = _expand_sport_affinities({"nba": 1.0})
        assert "basketball_nba" in result
        assert "basketball_ncaab" not in result
        assert result["basketball_nba"] == 1.0

    def test_split_college_basketball_expansion(self):
        """New 'college_basketball' key should expand to NCAAB + WNCAAB."""
        result = _expand_sport_affinities({"college_basketball": 0.3})
        assert "basketball_ncaab" in result
        assert "basketball_wncaab" in result
        assert "basketball_nba" not in result
        assert all(v == 0.3 for v in result.values())

    def test_legacy_basketball_expansion(self):
        """Legacy 'basketball' should expand to NBA, NCAAB, WNCAAB."""
        result = _expand_sport_affinities({"basketball": 0.3})
        assert "basketball_nba" in result
        assert "basketball_ncaab" in result
        assert "basketball_wncaab" in result
        assert all(v == 0.3 for v in result.values())

    def test_multiple_sports(self):
        """Multiple sports should all expand correctly."""
        result = _expand_sport_affinities({
            "nfl": 1.0,
            "college_football": 0.1,
            "hockey": 0.3,
        })
        assert result["americanfootball_nfl"] == 1.0
        assert result["americanfootball_ncaaf"] == 0.1
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

    def test_basic_compression_split_keys(self):
        """Backend keys should compress to split frontend categories (nfl, college_football)."""
        result = _compress_sport_affinities({
            "americanfootball_nfl": 1.0,
            "americanfootball_ncaaf": 0.3,
        })
        assert result == {"nfl": 1.0, "college_football": 0.3}

    def test_basketball_split_compression(self):
        """Basketball backend keys compress to split nba/college_basketball."""
        result = _compress_sport_affinities({
            "basketball_nba": 1.0,
            "basketball_ncaab": 0.3,
            "basketball_wncaab": 0.1,
        })
        # nba=1.0, college_basketball=max(0.3, 0.1)=0.3
        assert result == {"nba": 1.0, "college_basketball": 0.3}

    def test_multiple_categories(self):
        """Multiple categories should compress independently."""
        result = _compress_sport_affinities({
            "americanfootball_nfl": 1.0,
            "basketball_nba": 0.3,
            "icehockey_nhl": 0.1,
        })
        assert result == {"nfl": 1.0, "nba": 0.3, "hockey": 0.1}

    def test_unknown_keys_skipped(self):
        """Unknown backend keys should be skipped in compression."""
        result = _compress_sport_affinities({
            "americanfootball_nfl": 1.0,
            "unknown_sport_xyz": 0.5,
        })
        assert result == {"nfl": 1.0}
        assert "unknown_sport_xyz" not in result

    def test_empty_input(self):
        """Empty input should return empty dict."""
        assert _compress_sport_affinities({}) == {}

    def test_roundtrip_split_keys(self):
        """Expand then compress with split keys should roundtrip."""
        original = {"nfl": 1.0, "college_football": 0.3, "hockey": 0.1}
        expanded = _expand_sport_affinities(original)
        compressed = _compress_sport_affinities(expanded)
        assert compressed == original

    def test_legacy_roundtrip_produces_split_keys(self):
        """Expand legacy 'football' then compress produces split keys."""
        expanded = _expand_sport_affinities({"football": 1.0})
        compressed = _compress_sport_affinities(expanded)
        # Old "football" key expands to both NFL and NCAAF at 1.0,
        # then compresses to split keys
        assert compressed == {"nfl": 1.0, "college_football": 1.0}


# =============================================================================
# Onboarding Route Persistence Tests
# =============================================================================


class TestOnboardingRoutes:
    """Route-level guardrails for onboarding preferences."""

    @pytest.mark.asyncio
    async def test_submit_onboarding_persists_and_returns_category_interests(self):
        user = SimpleNamespace(id=42, email_preferences={})
        db = _FakeOnboardingDb()
        body = OnboardingRequest(
            home_location="Boston",
            sport_affinities={
                "politics": 1.0,
                "entertainment": 0.3,
                "nfl": 0.1,
            },
            raw_inputs={"source": "onboarding-test"},
        )

        result = await submit_onboarding(body=body, user=user, db=db)
        preferences = await get_preferences(user=user, db=db)

        assert result == {"status": "ok", "onboarding_completed": True}
        assert db.flush_count == 1
        assert db.preferences.home_location == "Boston"
        assert db.preferences.onboarding_completed is True
        assert db.preferences.onboarding_raw == {"source": "onboarding-test"}
        assert db.preferences.sport_affinities == {
            "politics": 1.0,
            "entertainment": 0.3,
            "americanfootball_nfl": 0.1,
        }
        assert preferences.sport_affinities == {
            "politics": 1.0,
            "entertainment": 0.3,
            "nfl": 0.1,
        }

    @pytest.mark.asyncio
    async def test_anonymous_preferences_return_empty_onboarding_defaults(self):
        db = _FakeOnboardingDb()

        preferences = await get_preferences(user=None, db=db)

        assert preferences.home_location is None
        assert preferences.sport_affinities == {}
        assert preferences.onboarding_completed is False
        assert preferences.favorites == []
        assert db.execute_count == 0


# =============================================================================
# Reverse Mapping Tests
# =============================================================================


class TestReverseMapping:
    """Tests for SPORT_KEY_TO_CATEGORY reverse mapping."""

    def test_all_backend_keys_mapped(self):
        """Every backend key used in SPORT_AFFINITY_MAPPING should have a reverse mapping."""
        all_backend_keys = set()
        for keys in SPORT_AFFINITY_MAPPING.values():
            all_backend_keys.update(keys)
        for key in all_backend_keys:
            assert key in SPORT_KEY_TO_CATEGORY, (
                f"Missing reverse mapping for {key}"
            )

    def test_split_keys_preferred(self):
        """Split keys (nfl, college_football) should be preferred over legacy (football)."""
        assert SPORT_KEY_TO_CATEGORY["americanfootball_nfl"] == "nfl"
        assert SPORT_KEY_TO_CATEGORY["americanfootball_ncaaf"] == "college_football"
        assert SPORT_KEY_TO_CATEGORY["basketball_nba"] == "nba"
        assert SPORT_KEY_TO_CATEGORY["basketball_ncaab"] == "college_basketball"
        assert SPORT_KEY_TO_CATEGORY["basketball_wncaab"] == "college_basketball"

    def test_nhl_maps_to_hockey(self):
        assert SPORT_KEY_TO_CATEGORY["icehockey_nhl"] == "hockey"

    def test_mlb_maps_to_baseball(self):
        assert SPORT_KEY_TO_CATEGORY["baseball_mlb"] == "baseball"

    def test_non_sports_mapped(self):
        """Non-sports categories should be mapped."""
        assert SPORT_KEY_TO_CATEGORY["politics"] == "politics"
        assert SPORT_KEY_TO_CATEGORY["entertainment"] == "entertainment"


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
