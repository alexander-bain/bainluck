"""Tests for market_moves route logic."""

from app.routes.market_moves import _PRIORITY_SPORT_KEYS


class TestPrioritySportKeys:
    """Verify the priority sport key set is constructed correctly."""

    def test_nba_is_priority(self):
        assert "basketball_nba" in _PRIORITY_SPORT_KEYS

    def test_nfl_is_priority(self):
        assert "americanfootball_nfl" in _PRIORITY_SPORT_KEYS

    def test_mlb_is_priority(self):
        assert "baseball_mlb" in _PRIORITY_SPORT_KEYS

    def test_nhl_is_priority(self):
        assert "icehockey_nhl" in _PRIORITY_SPORT_KEYS

    def test_ncaaf_is_priority(self):
        assert "americanfootball_ncaaf" in _PRIORITY_SPORT_KEYS

    def test_epl_is_priority(self):
        assert "soccer_epl" in _PRIORITY_SPORT_KEYS

    def test_minor_league_not_priority(self):
        assert "soccer_mexico_ligamx" not in _PRIORITY_SPORT_KEYS
        assert "boxing_boxing" not in _PRIORITY_SPORT_KEYS

    def test_no_tier_4_in_priority(self):
        """No tier 4 keys should be in priority set."""
        # Tier 4 is anything not in LEAGUE_TIERS, so check by exclusion
        assert "curling_whatever" not in _PRIORITY_SPORT_KEYS
