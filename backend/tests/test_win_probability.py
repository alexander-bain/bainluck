"""Tests for the statistical win probability model."""

import pytest
from datetime import datetime, timezone, timedelta
from app.utils.win_probability import (
    _normalize_sport_key,
    compute_statistical_win_prob,
    estimate_seconds_remaining_from_wall_clock,
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


# All sport keys that tasks.py actually passes (The Odds API convention).
# Every supported sport must work with both its canonical key AND its database key.
ALL_DB_SPORT_KEYS = [
    ("americanfootball_nfl", "7:30", "Q3", 21, 14),
    ("americanfootball_ncaaf", "7:30", "Q3", 21, 14),
    ("basketball_nba", "5:00", "Q4", 100, 95),
    ("basketball_ncaab", "5:00", "2nd Half", 60, 55),
    ("basketball_wncaab", "5:00", "Q4", 60, 55),
    ("icehockey_nhl", "10:00", "3rd Period", 3, 1),
]


class TestAllSportsWithDatabaseKeys:
    """Ensure every supported sport works when called with the actual database key.

    This is the critical integration-style test: tasks.py always passes
    The Odds API sport keys (e.g. americanfootball_nfl, icehockey_nhl),
    never canonical keys. If a sport silently returns None here, it means
    the stat model is broken for that sport in production.
    """

    @pytest.mark.parametrize("sport_key,clock,period,home,away", ALL_DB_SPORT_KEYS)
    def test_parse_game_clock_with_db_key(self, sport_key, clock, period, home, away):
        result = parse_game_clock(clock, period, sport_key)
        assert result is not None, f"parse_game_clock returned None for db key {sport_key!r}"
        assert result > 0

    @pytest.mark.parametrize("sport_key,clock,period,home,away", ALL_DB_SPORT_KEYS)
    def test_compute_win_prob_with_db_key(self, sport_key, clock, period, home, away):
        result = compute_statistical_win_prob(
            home_score=home, away_score=away,
            clock=clock, period=period,
            sport_key=sport_key,
            pregame_spread=-3,
        )
        assert result is not None, f"compute_statistical_win_prob returned None for db key {sport_key!r}"
        assert 0.001 <= result <= 0.999


class TestWallClockEstimation:
    """Test wall-clock time remaining estimation (fallback for ESPN mismatches)."""

    def test_game_not_started(self):
        """Before commence_time, should return None."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        result = estimate_seconds_remaining_from_wall_clock(future, "basketball_nba")
        assert result is None

    def test_none_commence_time(self):
        result = estimate_seconds_remaining_from_wall_clock(None, "basketball_nba")
        assert result is None

    def test_unsupported_sport(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = estimate_seconds_remaining_from_wall_clock(start, "cricket_test")
        assert result is None

    def test_nfl_just_started(self):
        """NFL game just started — most game time remaining."""
        start = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = estimate_seconds_remaining_from_wall_clock(start, "americanfootball_nfl")
        assert result is not None
        # Should be close to full game (3600s) but slightly less
        assert 3400 < result < 3600

    def test_nba_halftime(self):
        """NBA game about 1h 15m in — roughly halftime."""
        start = datetime.now(timezone.utc) - timedelta(minutes=75)
        result = estimate_seconds_remaining_from_wall_clock(start, "basketball_nba")
        assert result is not None
        # ~half of 2880s game clock remaining
        assert 1000 < result < 2000

    def test_nfl_nearly_over(self):
        """NFL game 3 hours in — very little time left."""
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        result = estimate_seconds_remaining_from_wall_clock(start, "americanfootball_nfl")
        assert result is not None
        assert result < 600  # Less than 10 game-minutes

    def test_game_past_expected_duration(self):
        """Game that's run past expected wall duration — should return None."""
        start = datetime.now(timezone.utc) - timedelta(hours=5)
        result = estimate_seconds_remaining_from_wall_clock(start, "basketball_nba")
        assert result is None

    def test_nhl_game(self):
        """NHL game 1 hour in."""
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        result = estimate_seconds_remaining_from_wall_clock(start, "icehockey_nhl")
        assert result is not None
        assert 1500 < result < 3000

    def test_ncaaf_game(self):
        """College football game uses NCAAF wall duration."""
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        result = estimate_seconds_remaining_from_wall_clock(
            start, "americanfootball_ncaaf"
        )
        assert result is not None
        assert result > 0

    def test_explicit_now_parameter(self):
        """Using explicit 'now' parameter instead of real clock."""
        start = datetime(2026, 2, 20, 19, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 20, 20, 30, 0, tzinfo=timezone.utc)  # 90 min later
        result = estimate_seconds_remaining_from_wall_clock(
            start, "basketball_nba", now=now
        )
        assert result is not None
        assert result > 0

    def test_sport_key_aliases_work(self):
        """Verify Odds API sport keys are properly aliased."""
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        nfl = estimate_seconds_remaining_from_wall_clock(start, "americanfootball_nfl")
        nhl = estimate_seconds_remaining_from_wall_clock(start, "icehockey_nhl")
        assert nfl is not None
        assert nhl is not None


class TestComputeWinProbWithWallClock:
    """Test that compute_statistical_win_prob uses wall-clock fallback."""

    def test_fallback_when_no_clock_no_period(self):
        """Without clock/period but with commence_time, should still compute."""
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        result = compute_statistical_win_prob(
            home_score=14, away_score=7,
            clock=None, period=None,
            sport_key="americanfootball_nfl",
            pregame_spread=-3,
            commence_time=start,
        )
        assert result is not None
        assert result > 0.5  # Home leading and favored

    def test_prefers_espn_clock_over_wall_clock(self):
        """When clock/period are available, should use them (not wall clock)."""
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        # With ESPN clock
        with_clock = compute_statistical_win_prob(
            home_score=14, away_score=14,
            clock="7:30", period="Q3",
            sport_key="americanfootball_nfl",
            pregame_spread=0,
            commence_time=start,
        )
        # Without ESPN clock (wall-clock fallback)
        without_clock = compute_statistical_win_prob(
            home_score=14, away_score=14,
            clock=None, period=None,
            sport_key="americanfootball_nfl",
            pregame_spread=0,
            commence_time=start,
        )
        # Both should return values but they'll differ because wall-clock
        # estimation is approximate
        assert with_clock is not None
        assert without_clock is not None
        # Both should be roughly 50% for tied game with no spread
        assert 0.4 < with_clock < 0.6
        assert 0.4 < without_clock < 0.6

    def test_no_clock_no_commence_returns_none(self):
        """Without clock AND commence_time, should return None."""
        result = compute_statistical_win_prob(
            home_score=14, away_score=7,
            clock=None, period=None,
            sport_key="americanfootball_nfl",
            commence_time=None,
        )
        assert result is None

    def test_nba_wall_clock_fallback(self):
        """NBA game using wall-clock fallback."""
        start = datetime.now(timezone.utc) - timedelta(minutes=90)
        result = compute_statistical_win_prob(
            home_score=55, away_score=48,
            clock=None, period=None,
            sport_key="basketball_nba",
            commence_time=start,
        )
        assert result is not None
        assert result > 0.5  # Home leading

    def test_ncaab_wall_clock_fallback(self):
        """College basketball — the primary use case for this fallback."""
        start = datetime.now(timezone.utc) - timedelta(minutes=60)
        result = compute_statistical_win_prob(
            home_score=35, away_score=30,
            clock=None, period=None,
            sport_key="basketball_ncaab",
            commence_time=start,
        )
        assert result is not None
        assert result > 0.5
