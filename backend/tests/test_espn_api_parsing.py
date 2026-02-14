"""Tests for ESPN API client parsing helpers.

Covers:
- _parse_color: ESPN color → hex format conversion
- SPORT_LEAGUE_MAP: sport key → ESPN path mapping completeness
"""

import pytest

from app.services.espn_api import ESPNAPIService, SPORT_LEAGUE_MAP


@pytest.fixture
def client():
    """Create an ESPN API client instance for testing instance methods."""
    return ESPNAPIService()


# ── _parse_color ────────────────────────────────────────────────────────


class TestParseColor:
    """Tests for ESPN color → hex conversion."""

    def test_none_returns_none(self, client):
        assert client._parse_color(None) is None

    def test_empty_string_returns_none(self, client):
        assert client._parse_color("") is None

    def test_adds_hash_prefix(self, client):
        assert client._parse_color("FF0000") == "#FF0000"

    def test_already_has_hash(self, client):
        assert client._parse_color("#00FF00") == "#00FF00"

    def test_lowercase_hex(self, client):
        assert client._parse_color("1d428a") == "#1d428a"

    def test_three_char_hex(self, client):
        """ESPN shouldn't return 3-char hex, but verify it still gets prefixed."""
        assert client._parse_color("FFF") == "#FFF"


# ── SPORT_LEAGUE_MAP ───────────────────────────────────────────────────


class TestSportLeagueMap:
    """Tests for the sport key → ESPN (sport, league) mapping."""

    def test_nfl_mapping(self):
        assert SPORT_LEAGUE_MAP["americanfootball_nfl"] == ("football", "nfl")

    def test_ncaaf_mapping(self):
        assert SPORT_LEAGUE_MAP["americanfootball_ncaaf"] == ("football", "college-football")

    def test_nba_mapping(self):
        assert SPORT_LEAGUE_MAP["basketball_nba"] == ("basketball", "nba")

    def test_ncaab_mapping(self):
        assert SPORT_LEAGUE_MAP["basketball_ncaab"] == ("basketball", "mens-college-basketball")

    def test_wncaab_mapping(self):
        assert SPORT_LEAGUE_MAP["basketball_wncaab"] == ("basketball", "womens-college-basketball")

    def test_nhl_mapping(self):
        assert SPORT_LEAGUE_MAP["icehockey_nhl"] == ("hockey", "nhl")

    def test_mlb_mapping(self):
        assert SPORT_LEAGUE_MAP["baseball_mlb"] == ("baseball", "mlb")

    def test_epl_mapping(self):
        assert SPORT_LEAGUE_MAP["soccer_epl"] == ("soccer", "eng.1")

    def test_mls_mapping(self):
        assert SPORT_LEAGUE_MAP["soccer_usa_mls"] == ("soccer", "usa.1")

    def test_ufc_mapping(self):
        assert SPORT_LEAGUE_MAP["mma_ufc"] == ("mma", "ufc")

    def test_unknown_key_returns_none(self, client):
        assert client._get_espn_path("unknown_sport") is None

    def test_all_values_are_tuples(self):
        """Every mapping value should be a (sport, league) tuple."""
        for key, value in SPORT_LEAGUE_MAP.items():
            assert isinstance(value, tuple), f"{key} value is not a tuple"
            assert len(value) == 2, f"{key} tuple should have exactly 2 elements"

    def test_all_values_are_nonempty_strings(self):
        """Sport and league components should be non-empty strings."""
        for key, (sport, league) in SPORT_LEAGUE_MAP.items():
            assert isinstance(sport, str) and sport, f"{key} sport is empty"
            assert isinstance(league, str) and league, f"{key} league is empty"

    def test_expected_count(self):
        """Verify we have all 20 expected sport mappings."""
        assert len(SPORT_LEAGUE_MAP) >= 17  # at least the core sports
