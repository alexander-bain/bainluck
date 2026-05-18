"""Tests for ESPN API boxscore and scoring play parsing.

Covers methods NOT already tested in test_espn_api_parsing.py:
- _parse_stat_value: compound stats, percentages, dashes
- _parse_boxscore: multi-team, stat normalization, double/triple-double
- _parse_scoring_plays: play types, missing fields, polymorphic type
"""

import json
from pathlib import Path

import pytest

from app.services.espn_api import ESPNAPIService


@pytest.fixture
def client():
    return ESPNAPIService()


@pytest.fixture
def fixtures():
    path = Path(__file__).parent / "fixtures" / "espn_boxscore_fixtures.json"
    with open(path) as f:
        return json.load(f)


# ── _parse_stat_value ─────────────────────────────────────────────────


class TestParseStatValue:

    def test_simple_integer(self):
        assert ESPNAPIService._parse_stat_value("28") == 28.0

    def test_simple_float(self):
        assert ESPNAPIService._parse_stat_value("3.5") == 3.5

    def test_compound_made_attempts(self):
        """'10-22' (made-attempts) → extracts made value 10.0."""
        assert ESPNAPIService._parse_stat_value("10-22") == 10.0

    def test_compound_single_digit(self):
        assert ESPNAPIService._parse_stat_value("4-10") == 4.0

    def test_percentage(self):
        assert ESPNAPIService._parse_stat_value(".455") == pytest.approx(0.455)

    def test_dash_returns_none(self):
        assert ESPNAPIService._parse_stat_value("--") is None

    def test_single_dash_returns_none(self):
        assert ESPNAPIService._parse_stat_value("-") is None

    def test_empty_string_returns_none(self):
        assert ESPNAPIService._parse_stat_value("") is None

    def test_negative_number(self):
        """Negative numbers like '-3' should parse correctly."""
        assert ESPNAPIService._parse_stat_value("-3") == -3.0

    def test_zero(self):
        assert ESPNAPIService._parse_stat_value("0") == 0.0

    def test_whitespace_stripped(self):
        assert ESPNAPIService._parse_stat_value("  28  ") == 28.0

    def test_whitespace_only_returns_none(self):
        assert ESPNAPIService._parse_stat_value("   ") is None


# ── _parse_boxscore ───────────────────────────────────────────────────


class TestParseBoxscore:

    def test_basketball_two_teams(self, client, fixtures):
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        assert "Jayson Tatum" in result
        assert "Jaylen Brown" in result
        assert "LeBron James" in result

    def test_stat_normalization(self, client, fixtures):
        """ESPN abbreviations normalized to canonical names."""
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        tatum = result["Jayson Tatum"]
        assert "points" in tatum
        assert "rebounds" in tatum
        assert "assists" in tatum
        assert "steals" in tatum
        assert "blocks" in tatum
        assert "turnovers" in tatum

    def test_stat_values_correct(self, client, fixtures):
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        tatum = result["Jayson Tatum"]
        assert tatum["points"] == 32.0
        assert tatum["rebounds"] == 8.0
        assert tatum["assists"] == 5.0
        assert tatum["steals"] == 2.0
        assert tatum["minutes"] == 38.0

    def test_compound_stats_extract_made(self, client, fixtures):
        """'11-22' for FG → field goals = 11."""
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        tatum = result["Jayson Tatum"]
        assert tatum["field goals"] == 11.0
        assert tatum["three pointers"] == 4.0
        assert tatum["free throws"] == 6.0

    def test_double_double_detected(self, client, fixtures):
        """Jaylen Brown: 28 pts, 11 reb → double-double."""
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        brown = result["Jaylen Brown"]
        assert brown["points"] == 28.0
        assert brown["rebounds"] == 11.0
        assert brown.get("double doubles") == 1

    def test_triple_double_detected(self, client, fixtures):
        """LeBron: 35 pts, 12 reb, 10 ast → triple-double."""
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        lebron = result["LeBron James"]
        assert lebron["points"] == 35.0
        assert lebron["rebounds"] == 12.0
        assert lebron["assists"] == 10.0
        assert lebron.get("double doubles") == 1
        assert lebron.get("triple doubles") == 1

    def test_dedicated_triple_double_fixture(self, client, fixtures):
        """Jokic: 22 pts, 14 reb, 11 ast → triple-double."""
        result = client._parse_boxscore(fixtures["boxscore_triple_double"])
        jokic = result["Nikola Jokic"]
        assert jokic.get("triple doubles") == 1

    def test_no_double_double_below_threshold(self, client, fixtures):
        """Tatum: 32 pts, 8 reb, 5 ast → only 1 category ≥ 10, no DD."""
        result = client._parse_boxscore(fixtures["boxscore_basketball"])
        tatum = result["Jayson Tatum"]
        assert "double doubles" not in tatum

    def test_multi_stat_group_merged(self, client, fixtures):
        """Player appearing in multiple stat groups gets stats merged."""
        result = client._parse_boxscore(fixtures["boxscore_multi_stat_group"])
        player = result["Player One"]
        assert player["points"] == 20.0
        assert player["rebounds"] == 5.0
        assert player["assists"] == 3.0
        assert player["steals"] == 2.0
        assert player["blocks"] == 1.0
        assert player["turnovers"] == 4.0

    def test_mismatched_stat_lengths_skipped(self, client, fixtures):
        """Players with len(stats) != len(names) are skipped."""
        result = client._parse_boxscore(fixtures["boxscore_mismatched_lengths"])
        assert "Bad Data Player" not in result

    def test_unknown_and_blank_stats_do_not_drop_player(self, client):
        """Bad individual stat cells are ignored while valid player stats survive."""
        result = client._parse_boxscore(
            {
                "boxscore": {
                    "players": [
                        {
                            "statistics": [
                                {
                                    "names": ["PTS", "REB", "MYSTERY", "AST", "BLK"],
                                    "athletes": [
                                        {
                                            "athlete": {"displayName": "Partial Data Player"},
                                            "stats": ["12", "--", "999", "", "2"],
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            }
        )

        assert result["Partial Data Player"] == {
            "points": 12.0,
            "blocks": 2.0,
        }

    def test_empty_boxscore(self, client, fixtures):
        result = client._parse_boxscore(fixtures["boxscore_empty"])
        assert result == {}

    def test_no_boxscore_key(self, client, fixtures):
        result = client._parse_boxscore(fixtures["boxscore_no_key"])
        assert result == {}


# ── _parse_scoring_plays ──────────────────────────────────────────────


class TestParseScoringPlays:

    def test_full_scoring_play(self, client, fixtures):
        plays = client._parse_scoring_plays(fixtures["scoring_plays_full"])
        assert len(plays) == 2

        play = plays[0]
        assert play["description"] == "J. Tatum makes 24-foot three point jumper"
        assert play["short_text"] == "J. Tatum 24' 3PT"
        assert play["type"] == "Three Point Jumper"
        assert play["period"] == 1
        assert play["clock"] == "9:42"
        assert play["home_score"] == 3
        assert play["away_score"] == 0
        assert play["team"] == "Boston Celtics"

    def test_second_play(self, client, fixtures):
        plays = client._parse_scoring_plays(fixtures["scoring_plays_full"])
        play = plays[1]
        assert play["type"] == "Layup"
        assert play["home_score"] == 3
        assert play["away_score"] == 2
        assert play["team"] == "Los Angeles Lakers"

    def test_minimal_play(self, client, fixtures):
        """Play with only text and scores, missing type/period/clock/team."""
        plays = client._parse_scoring_plays(fixtures["scoring_plays_minimal"])
        assert len(plays) == 1
        play = plays[0]
        assert play["description"] == "Goal scored"
        assert play["type"] == ""
        assert play["period"] is None
        assert play["clock"] == ""
        assert play["team"] == ""
        assert play["home_score"] == 1
        assert play["away_score"] == 0

    def test_type_as_string(self, client, fixtures):
        """Type can be a string instead of dict."""
        plays = client._parse_scoring_plays(fixtures["scoring_plays_type_string"])
        assert len(plays) == 1
        assert plays[0]["type"] == "Touchdown"
        assert plays[0]["period"] == 2
        assert plays[0]["clock"] == "5:30"

    def test_empty_scoring_plays(self, client, fixtures):
        plays = client._parse_scoring_plays(fixtures["scoring_plays_empty"])
        assert plays == []

    def test_no_scoring_plays_key(self, client):
        plays = client._parse_scoring_plays({})
        assert plays == []
