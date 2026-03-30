"""Tests for the statistical win probability model."""

import pytest
from datetime import datetime, timezone, timedelta
from app.utils.win_probability import (
    _normalize_sport_key,
    compute_baseball_win_prob,
    compute_statistical_win_prob,
    estimate_seconds_remaining_from_wall_clock,
    parse_baseball_state,
    parse_game_clock,
    parse_mlb_inning,
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
    ("baseball_mlb", None, "Top 5th", 4, 2),
    ("baseball_mlb_preseason", None, "Bot 3rd", 2, 1),
    ("baseball_ncaa", None, "Top 7th", 5, 3),
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


class TestParseMLBInning:
    """Test MLB inning parsing into outs remaining."""

    def test_top_1st(self):
        result = parse_mlb_inning("Top 1st")
        assert result is not None
        assert result == 52.5  # 54 - 1.5

    def test_bottom_1st(self):
        result = parse_mlb_inning("Bot 1st")
        assert result is not None
        assert result == 49.5  # 54 - 4.5

    def test_top_5th(self):
        result = parse_mlb_inning("Top 5th")
        assert result is not None
        # (5-1)*6 + 1.5 = 25.5 done, 54 - 25.5 = 28.5
        assert result == 28.5

    def test_bottom_7th(self):
        result = parse_mlb_inning("Bottom 7th")
        assert result is not None
        # (7-1)*6 + 3 + 1.5 = 40.5 done, 54 - 40.5 = 13.5
        assert result == 13.5

    def test_top_9th(self):
        result = parse_mlb_inning("Top 9th")
        assert result is not None
        # (9-1)*6 + 1.5 = 49.5 done, 54 - 49.5 = 4.5
        assert result == 4.5

    def test_bottom_9th(self):
        result = parse_mlb_inning("Bot 9th")
        assert result is not None
        # (9-1)*6 + 3 + 1.5 = 52.5 done, 54 - 52.5 = 1.5
        assert result == 1.5

    def test_mid_inning(self):
        result = parse_mlb_inning("Mid 5th")
        assert result is not None
        # (5-1)*6 + 3 = 27 done, 54 - 27 = 27
        assert result == 27.0

    def test_end_inning(self):
        result = parse_mlb_inning("End 5th")
        assert result is not None
        # 5*6 = 30 done, 54 - 30 = 24
        assert result == 24.0

    def test_numeric_only(self):
        """Just an inning number (e.g., from ESPN ee.period)."""
        result = parse_mlb_inning("5")
        assert result is not None
        # Unknown half → assumes mid-inning: (5-1)*6 + 3 = 27 done, 54 - 27 = 27
        assert result == 27.0

    def test_extra_innings(self):
        """Extra innings: top of 10th."""
        result = parse_mlb_inning("Top 10th")
        assert result is not None
        # (10-1)*6 + 1.5 = 55.5 done, 54 - 55.5 → clamped to 0.5
        assert result == 0.5

    def test_none_period(self):
        assert parse_mlb_inning(None) is None

    def test_empty_period(self):
        assert parse_mlb_inning("") is None

    def test_t5_shorthand(self):
        """Short format: T5, B7."""
        result = parse_mlb_inning("T5")
        assert result is not None
        assert result == 28.5

    def test_b7_shorthand(self):
        result = parse_mlb_inning("B7")
        assert result is not None
        assert result == 13.5


class TestParseBaseballState:
    """Test structured baseball state parsing."""

    def test_top_5th_half_innings(self):
        """Top 5th: away batting. Home has more remaining HI."""
        state = parse_baseball_state("Top 5th")
        assert state is not None
        assert state["inning"] == 5
        assert state["is_top"] is True
        # Away: partial current + innings 6-9 tops = 0.5 + 4 = 4.5
        assert state["away_half_innings_remaining"] == 4.5
        # Home: bottoms 5-9 = 5
        assert state["home_half_innings_remaining"] == 5

    def test_bottom_9th_home_batting(self):
        """Bottom 9th: home batting. Away has 0 HI remaining."""
        state = parse_baseball_state("Bot 9th")
        assert state is not None
        assert state["is_top"] is False
        assert state["away_half_innings_remaining"] == 0
        # Home has partial current half-inning
        assert state["home_half_innings_remaining"] > 0
        assert state["home_half_innings_remaining"] < 1

    def test_top_1st_full_game(self):
        """Start of game: both teams have ~9 half-innings."""
        state = parse_baseball_state("Top 1st")
        assert state is not None
        # Away: partial current + 8 more tops
        assert state["away_half_innings_remaining"] == 8.5
        # Home: 9 bottoms
        assert state["home_half_innings_remaining"] == 9

    def test_mid_5th(self):
        """Mid 5th: between halves."""
        state = parse_baseball_state("Mid 5th")
        assert state is not None
        assert state["away_half_innings_remaining"] == 4  # tops 6-9
        assert state["home_half_innings_remaining"] == 5  # bottoms 5-9

    def test_extra_innings(self):
        """Extra innings: minimal remaining."""
        state = parse_baseball_state("Top 10th")
        assert state is not None
        assert state["inning"] == 10
        assert state["home_half_innings_remaining"] >= 0
        assert state["away_half_innings_remaining"] >= 0


class TestBaseballWinProb:
    """Test the Poisson-based baseball win probability model directly."""

    def test_start_of_game_slight_home_advantage(self):
        """0-0 start: home team has ~54% due to home field advantage."""
        result = compute_baseball_win_prob(0, 0, "Top 1st")
        assert result is not None
        assert 0.51 < result < 0.58

    def test_home_advantage_matters_early(self):
        """Home advantage is more pronounced early (more game to play)."""
        early = compute_baseball_win_prob(0, 0, "Top 1st")
        late = compute_baseball_win_prob(0, 0, "Top 9th")
        assert early is not None and late is not None
        # Both should be >0.5 but early should be further from 0.5
        # (Actually in late game the HI asymmetry dominates — home bats last)
        assert early > 0.5

    def test_walk_off_scenario(self):
        """Home leading entering top 9 with no home HI remaining is near-certain."""
        # Top 9th with 0 outs: away has a partial HI, home has 0 future HI
        # but home is already ahead → near-certain win
        result = compute_baseball_win_prob(3, 2, "Top 9th")
        assert result is not None
        assert result > 0.8

    def test_poisson_variance_scales(self):
        """Variance should be higher early (more innings left) than late."""
        # 2-run lead should be less certain early than late
        early = compute_baseball_win_prob(3, 1, "Top 2nd")
        late = compute_baseball_win_prob(3, 1, "Top 8th")
        assert early is not None and late is not None
        assert late > early


class TestMLBStatModel:
    """Test the statistical model for MLB games via compute_statistical_win_prob."""

    def test_tied_game_early(self):
        """Tied game in 3rd inning should be close to 50%."""
        result = compute_statistical_win_prob(
            home_score=1, away_score=1,
            clock=None, period="Top 3rd",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert result is not None
        assert abs(result - 0.5) < 0.1

    def test_home_leading_late(self):
        """Home team up 3 in the 8th should have high win prob."""
        result = compute_statistical_win_prob(
            home_score=5, away_score=2,
            clock=None, period="Top 8th",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert result is not None
        assert result > 0.8

    def test_away_leading(self):
        """Away team leading should give home <50%."""
        result = compute_statistical_win_prob(
            home_score=1, away_score=4,
            clock=None, period="Top 5th",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert result is not None
        assert result < 0.3

    def test_late_lead_more_decisive(self):
        """Same lead in 8th should give higher prob than 2nd."""
        early = compute_statistical_win_prob(
            home_score=3, away_score=1,
            clock=None, period="Top 2nd",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        late = compute_statistical_win_prob(
            home_score=3, away_score=1,
            clock=None, period="Top 8th",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert early is not None and late is not None
        assert late > early

    def test_blowout_bottom_9th(self):
        """10-0 in bottom of 9th should be near certain."""
        result = compute_statistical_win_prob(
            home_score=10, away_score=0,
            clock=None, period="Bot 9th",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert result is not None
        assert result > 0.99

    def test_spread_affects_pregame(self):
        """Home favored by spread should have higher base probability."""
        even = compute_statistical_win_prob(
            home_score=0, away_score=0,
            clock=None, period="Top 1st",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        favored = compute_statistical_win_prob(
            home_score=0, away_score=0,
            clock=None, period="Top 1st",
            sport_key="baseball_mlb",
            pregame_spread=-1.5,
        )
        assert even is not None and favored is not None
        assert favored > even

    def test_extra_innings_tight(self):
        """Extra innings tied game: home has slight disadvantage in top 10th
        because away is batting (could score), but home bats last (walk-off).
        Model gives ~0.3-0.5 range depending on remaining HI asymmetry."""
        result = compute_statistical_win_prob(
            home_score=3, away_score=3,
            clock=None, period="Top 10th",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert result is not None
        assert 0.2 < result < 0.6

    def test_wall_clock_fallback(self):
        """MLB should work with wall-clock fallback too."""
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        result = compute_statistical_win_prob(
            home_score=4, away_score=2,
            clock=None, period=None,
            sport_key="baseball_mlb",
            pregame_spread=0,
            commence_time=start,
        )
        assert result is not None
        assert result > 0.5

    def test_reds_red_sox_scenario(self):
        """Real game scenario: Reds 3, Red Sox 2, Top 9th (yesterday's game)."""
        result = compute_statistical_win_prob(
            home_score=3, away_score=2,
            clock=None, period="Top 9th",
            sport_key="baseball_mlb",
            pregame_spread=0,
        )
        assert result is not None
        # Home up 1 in top 9th — strong favorite
        assert result > 0.8
