"""Tests for the game-markets endpoint helpers."""

import pytest
from app.routes.events import _classify_game_market, _extract_threshold, _estimate_game_pace


class TestClassifyGameMarket:
    def test_game_total(self):
        assert _classify_game_market("Boston at Atlanta: Total Points") == "game_total"

    def test_over_under(self):
        assert _classify_game_market("Over 224.5") == "game_total"

    def test_under(self):
        assert _classify_game_market("Under 218.5") == "game_total"

    def test_team_total(self):
        assert _classify_game_market("Team Total Points") == "team_total"

    def test_half_total(self):
        assert _classify_game_market("1st Half Total") == "half_total"

    def test_quarter_total(self):
        assert _classify_game_market("1st Quarter Total") == "quarter_total"

    def test_player_prop_points(self):
        assert _classify_game_market("Boston at Atlanta: Trae Young Points") == "player_prop"

    def test_player_prop_assists(self):
        assert _classify_game_market("Jaylen Brown Assists") == "player_prop"

    def test_player_prop_rebounds(self):
        assert _classify_game_market("Rebounds Over 8.5") == "player_prop"

    def test_team_stat_points(self):
        assert _classify_game_market("Cleveland at Los Angeles L: Points") == "team_total"

    def test_team_stat_rebounds(self):
        assert _classify_game_market("Cleveland at Los Angeles L: Rebounds") == "team_total"

    def test_team_stat_assists(self):
        assert _classify_game_market("Boston at Atlanta: Assists") == "team_total"

    def test_team_stat_steals(self):
        assert _classify_game_market("Portland at Denver: Steals") == "team_total"

    def test_spread(self):
        assert _classify_game_market("Spread -4.5") == "spread"

    def test_moneyline(self):
        assert _classify_game_market("Moneyline") == "moneyline"

    def test_winner(self):
        assert _classify_game_market("Game Winner") == "moneyline"


class TestExtractThreshold:
    def test_over(self):
        assert _extract_threshold("Over 224.5") == 224.5

    def test_under(self):
        assert _extract_threshold("Under 218.5") == 218.5

    def test_integer(self):
        assert _extract_threshold("Over 220") == 220.0

    def test_no_number(self):
        assert _extract_threshold("No threshold") is None


class TestEstimateGamePace:
    def test_basketball_q3(self):
        pace = _estimate_game_pace(82, 74, "3rd Quarter", "6:55", "basketball_nba")
        assert pace is not None
        assert pace["total_scored"] == 156
        assert pace["projected_total"] is not None
        assert pace["projected_total"] > 156  # Should project higher
        assert pace["fraction_elapsed"] > 0.4

    def test_basketball_with_clock_prefix(self):
        pace = _estimate_game_pace(82, 74, "6:55 - 3rd Quarter", "6:55", "basketball_nba")
        assert pace is not None
        assert pace["total_scored"] == 156

    def test_halftime(self):
        pace = _estimate_game_pace(55, 52, "Halftime", "", "basketball_nba")
        assert pace is not None
        assert pace["fraction_elapsed"] == pytest.approx(0.5, abs=0.05)

    def test_no_scores(self):
        assert _estimate_game_pace(None, None, "Q1", "10:00", "basketball_nba") is None

    def test_no_period(self):
        assert _estimate_game_pace(10, 8, None, "10:00", "basketball_nba") is None

    def test_unknown_sport(self):
        assert _estimate_game_pace(10, 8, "Period 1", "10:00", "unknown_sport") is None

    def test_football_q2(self):
        pace = _estimate_game_pace(14, 7, "2nd Quarter", "8:00", "americanfootball_nfl")
        assert pace is not None
        assert pace["total_scored"] == 21
        assert pace["projected_total"] is not None

    def test_overtime(self):
        pace = _estimate_game_pace(110, 108, "OT", "", "basketball_nba")
        assert pace is not None
        assert pace["fraction_elapsed"] == 1.0
