"""Tests for the statistical win probability model."""

import pytest
from app.utils.win_probability import (
    _normalize_sport_key,
    compute_statistical_win_prob,
    parse_game_clock,
)


class TestParseGameClock:
    """Test game clock parsing for various sports."""

    def test_nfl_q1_full(self):
        result = parse_game_clock("15:00", "Q1", "football_nfl")
        assert result == 3600  # Full game

    def test_nfl_q4_two_minutes(self):
        result = parse_game_clock("2:00", "Q4", "football_nfl")
        assert result == 120

    def test_nfl_halftime(self):
        result = parse_game_clock("0:00", "Halftime", "football_nfl")
        assert result == 1800

    def test_nfl_overtime(self):
        result = parse_game_clock("8:00", "OT", "football_nfl")
        assert result == 150  # OT returns fixed 150s

    def test_nba_q1(self):
        result = parse_game_clock("10:00", "Q1", "basketball_nba")
        assert result == 2760  # 3 * 720 + 600

    def test_nba_q4(self):
        result = parse_game_clock("5:00", "Q4", "basketball_nba")
        assert result == 300

    def test_ncaab_first_half(self):
        result = parse_game_clock("10:00", "1st Half", "basketball_ncaab")
        assert result == 1800  # 1200 + 600

    def test_ncaab_second_half(self):
        result = parse_game_clock("5:00", "2nd Half", "basketball_ncaab")
        assert result == 300

    def test_nhl_first_period(self):
        result = parse_game_clock("15:00", "1st Period", "hockey_nhl")
        assert result == 3300  # 2 * 1200 + 900

    def test_nhl_third_period(self):
        result = parse_game_clock("5:00", "3rd Period", "hockey_nhl")
        assert result == 300

    def test_invalid_sport(self):
        result = parse_game_clock("5:00", "Q1", "tennis_atp")
        assert result is None

    def test_none_clock(self):
        result = parse_game_clock(None, "Q1", "football_nfl")
        assert result is None

    def test_none_period(self):
        result = parse_game_clock("5:00", None, "football_nfl")
        assert result is None


class TestComputeStatisticalWinProb:
    """Test the main win probability computation."""

    def test_tied_game_no_spread(self):
        """Tied game with no spread should be ~50%."""
        result = compute_statistical_win_prob(
            home_score=14, away_score=14,
            clock="7:30", period="Q3",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert abs(result - 0.5) < 0.05  # Close to 50%

    def test_home_leading_increases_prob(self):
        """Home team leading should have >50% win probability."""
        result = compute_statistical_win_prob(
            home_score=21, away_score=14,
            clock="7:30", period="Q3",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert result > 0.5

    def test_away_leading_decreases_prob(self):
        """Away team leading should give home <50%."""
        result = compute_statistical_win_prob(
            home_score=14, away_score=21,
            clock="7:30", period="Q3",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert result < 0.5

    def test_late_game_lead_more_decisive(self):
        """Same lead in Q4 should give higher probability than Q1."""
        q1_prob = compute_statistical_win_prob(
            home_score=7, away_score=0,
            clock="7:30", period="Q1",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        q4_prob = compute_statistical_win_prob(
            home_score=7, away_score=0,
            clock="7:30", period="Q4",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert q1_prob is not None and q4_prob is not None
        assert q4_prob > q1_prob  # Lead more meaningful late

    def test_spread_favoring_home(self):
        """Home team favored by spread should have higher base probability."""
        even_prob = compute_statistical_win_prob(
            home_score=0, away_score=0,
            clock="15:00", period="Q1",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        favored_prob = compute_statistical_win_prob(
            home_score=0, away_score=0,
            clock="15:00", period="Q1",
            sport_key="football_nfl",
            pregame_spread=-7,  # Home favored by 7
        )
        assert even_prob is not None and favored_prob is not None
        assert favored_prob > even_prob

    def test_none_spread_treated_as_zero(self):
        """None spread should give same result as spread=0."""
        with_none = compute_statistical_win_prob(
            home_score=14, away_score=7,
            clock="7:30", period="Q3",
            sport_key="football_nfl",
            pregame_spread=None,
        )
        with_zero = compute_statistical_win_prob(
            home_score=14, away_score=7,
            clock="7:30", period="Q3",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert with_none == with_zero

    def test_result_clamped(self):
        """Result should always be between 0.001 and 0.999."""
        # Huge lead late in the game
        result = compute_statistical_win_prob(
            home_score=42, away_score=0,
            clock="0:30", period="Q4",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert 0.001 <= result <= 0.999

    def test_nba_game(self):
        """NBA game should also work."""
        result = compute_statistical_win_prob(
            home_score=100, away_score=95,
            clock="3:00", period="Q4",
            sport_key="basketball_nba",
            pregame_spread=0,
        )
        assert result is not None
        assert result > 0.5  # Home leading

    def test_nhl_game(self):
        """NHL game should work with lower variance."""
        result = compute_statistical_win_prob(
            home_score=3, away_score=1,
            clock="10:00", period="3rd Period",
            sport_key="hockey_nhl",
            pregame_spread=0,
        )
        assert result is not None
        assert result > 0.7  # 2-goal lead in 3rd is very strong in hockey

    def test_unsupported_sport_returns_none(self):
        """Unsupported sports should return None."""
        result = compute_statistical_win_prob(
            home_score=1, away_score=0,
            clock="45:00", period="2nd Half",
            sport_key="soccer_epl",
        )
        assert result is None

    def test_invalid_clock_returns_none(self):
        """Invalid clock string should return None."""
        result = compute_statistical_win_prob(
            home_score=14, away_score=7,
            clock="invalid", period="Q1",
            sport_key="football_nfl",
        )
        assert result is None


class TestSuperBowlScenarios:
    """Test realistic Super Bowl scenarios."""

    def test_kickoff_even_spread(self):
        """Start of Super Bowl with even spread should be ~50%."""
        result = compute_statistical_win_prob(
            home_score=0, away_score=0,
            clock="15:00", period="Q1",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert abs(result - 0.5) < 0.01

    def test_kickoff_with_spread(self):
        """Start of game with -3 spread (home favored)."""
        result = compute_statistical_win_prob(
            home_score=0, away_score=0,
            clock="15:00", period="Q1",
            sport_key="football_nfl",
            pregame_spread=-3,
        )
        assert result is not None
        assert 0.55 < result < 0.65  # Home slightly favored

    def test_halftime_tie(self):
        """Halftime with tied score."""
        result = compute_statistical_win_prob(
            home_score=14, away_score=14,
            clock="0:00", period="Halftime",
            sport_key="football_nfl",
            pregame_spread=-3,
        )
        assert result is not None
        # Home was pregame favorite, tied at half, still slightly favored
        assert result > 0.5

    def test_two_minute_warning_close(self):
        """Two-minute warning with 3-point lead."""
        result = compute_statistical_win_prob(
            home_score=24, away_score=21,
            clock="2:00", period="Q4",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert 0.6 < result < 0.9  # Leading but game not over

    def test_final_seconds_blowout(self):
        """Last seconds of a blowout."""
        result = compute_statistical_win_prob(
            home_score=35, away_score=10,
            clock="0:10", period="Q4",
            sport_key="football_nfl",
            pregame_spread=0,
        )
        assert result is not None
        assert result > 0.99  # Game is over


class TestSportKeyAliases:
    """Test that Odds API sport key aliases work identically to canonical keys.

    The database stores sport keys using The Odds API convention
    (americanfootball_nfl, icehockey_nhl) but the model uses canonical
    keys (football_nfl, hockey_nhl). The alias mapping must be transparent.
    """

    def test_normalize_nfl(self):
        assert _normalize_sport_key("americanfootball_nfl") == "football_nfl"

    def test_normalize_ncaaf(self):
        assert _normalize_sport_key("americanfootball_ncaaf") == "football_ncaaf"

    def test_normalize_nhl(self):
        assert _normalize_sport_key("icehockey_nhl") == "hockey_nhl"

    def test_normalize_passthrough(self):
        """Keys that don't need aliasing should pass through unchanged."""
        assert _normalize_sport_key("basketball_nba") == "basketball_nba"
        assert _normalize_sport_key("football_nfl") == "football_nfl"

    def test_parse_clock_americanfootball_nfl(self):
        """parse_game_clock should work with americanfootball_nfl."""
        canonical = parse_game_clock("7:30", "Q3", "football_nfl")
        aliased = parse_game_clock("7:30", "Q3", "americanfootball_nfl")
        assert canonical is not None
        assert aliased == canonical

    def test_parse_clock_americanfootball_ncaaf(self):
        """parse_game_clock should work with americanfootball_ncaaf."""
        canonical = parse_game_clock("10:00", "Q2", "football_ncaaf")
        aliased = parse_game_clock("10:00", "Q2", "americanfootball_ncaaf")
        assert canonical is not None
        assert aliased == canonical

    def test_parse_clock_icehockey_nhl(self):
        """parse_game_clock should work with icehockey_nhl."""
        canonical = parse_game_clock("15:00", "1st Period", "hockey_nhl")
        aliased = parse_game_clock("15:00", "1st Period", "icehockey_nhl")
        assert canonical is not None
        assert aliased == canonical

    def test_compute_win_prob_americanfootball_nfl(self):
        """compute_statistical_win_prob should work with americanfootball_nfl."""
        canonical = compute_statistical_win_prob(
            home_score=21, away_score=14,
            clock="7:30", period="Q3",
            sport_key="football_nfl",
            pregame_spread=-3,
        )
        aliased = compute_statistical_win_prob(
            home_score=21, away_score=14,
            clock="7:30", period="Q3",
            sport_key="americanfootball_nfl",
            pregame_spread=-3,
        )
        assert canonical is not None
        assert aliased == canonical

    def test_compute_win_prob_icehockey_nhl(self):
        """compute_statistical_win_prob should work with icehockey_nhl."""
        canonical = compute_statistical_win_prob(
            home_score=3, away_score=1,
            clock="10:00", period="3rd Period",
            sport_key="hockey_nhl",
            pregame_spread=0,
        )
        aliased = compute_statistical_win_prob(
            home_score=3, away_score=1,
            clock="10:00", period="3rd Period",
            sport_key="icehockey_nhl",
            pregame_spread=0,
        )
        assert canonical is not None
        assert aliased == canonical

    def test_super_bowl_with_odds_api_key(self):
        """Simulate exactly how tasks.py calls the model for a Super Bowl game."""
        result = compute_statistical_win_prob(
            home_score=14, away_score=10,
            clock="5:00", period="Q3",
            sport_key="americanfootball_nfl",  # This is what tasks.py passes
            pregame_spread=-1.5,
        )
        assert result is not None
        assert result > 0.5  # Home team leading
