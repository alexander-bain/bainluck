"""Tests for the game-markets endpoint helpers."""

import pytest
from app.routes.events import _classify_game_market, _extract_threshold, _estimate_game_pace, _PLAYER_OUTCOME_RE


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

    # ── Ticker-based period classification (2H / quarter) ──────────────
    # Kalshi market names are often just "Celtics at Warriors" with the
    # period encoded only in the ticker prefix (e.g. KXNBA2HSPREAD-…).

    def test_2h_spread_via_ticker(self):
        """2nd half spread ticker with a generic matchup name."""
        assert _classify_game_market(
            "Celtics at Warriors", external_id="KXNBA2HSPREAD-26MAY14BOSGSW"
        ) == "half_spread"

    def test_2h_total_via_ticker(self):
        assert _classify_game_market(
            "Celtics at Warriors", external_id="KXNBA2HTOTAL-26MAY14BOSGSW"
        ) == "half_total"

    def test_2h_winner_via_ticker(self):
        assert _classify_game_market(
            "Celtics at Warriors", external_id="KXNBA2HWINNER-26MAY14BOSGSW"
        ) == "half_winner"

    def test_1h_spread_via_ticker(self):
        """1st half should also work via ticker (consistency check)."""
        assert _classify_game_market(
            "Celtics at Warriors", external_id="KXNBA1HSPREAD-26MAY14BOSGSW"
        ) == "half_spread"

    def test_quarter_total_via_ticker(self):
        assert _classify_game_market(
            "Celtics at Warriors", external_id="KXNBA3QTOTAL-26MAY14BOSGSW"
        ) == "quarter_total"

    def test_nfl_2h_spread_via_ticker(self):
        assert _classify_game_market(
            "Chiefs at Eagles", external_id="KXNFL2HSPREAD-26FEB09KCEPHI"
        ) == "half_spread"

    def test_name_still_wins_when_explicit(self):
        """When the name already says '1st Half Total', the ticker is irrelevant."""
        assert _classify_game_market(
            "1st Half Total", external_id="KXNBA2HTOTAL-26MAY14BOSGSW"
        ) == "half_total"

    def test_no_ticker_returns_other(self):
        """A bare matchup name with no ticker stays 'other'."""
        assert _classify_game_market("Celtics at Warriors") == "other"


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


class TestPlayerOutcomeRegex:
    """Tests for _PLAYER_OUTCOME_RE — detects player props hiding in team stat markets."""

    def test_simple_name(self):
        assert _PLAYER_OUTCOME_RE.match("Joel Embiid: 1+")

    def test_initials(self):
        assert _PLAYER_OUTCOME_RE.match("VJ Edgecombe: 1+")

    def test_suffix_jr(self):
        assert _PLAYER_OUTCOME_RE.match("Kelly Oubre Jr.: 1+")

    def test_apostrophe(self):
        assert _PLAYER_OUTCOME_RE.match("De'Aaron Fox: 3+")

    def test_hyphenated(self):
        assert _PLAYER_OUTCOME_RE.match("Shai Gilgeous-Alexander: 2+")

    def test_high_threshold(self):
        assert _PLAYER_OUTCOME_RE.match("Jaylen Brown: 30+")

    def test_over_not_player(self):
        assert not _PLAYER_OUTCOME_RE.match("Over 224.5 points scored")

    def test_under_not_player(self):
        assert not _PLAYER_OUTCOME_RE.match("Under 218.5")

    def test_total_not_player(self):
        assert not _PLAYER_OUTCOME_RE.match("Total: 3+")

    def test_yes_no_not_player(self):
        assert not _PLAYER_OUTCOME_RE.match("Yes")
        assert not _PLAYER_OUTCOME_RE.match("No")
