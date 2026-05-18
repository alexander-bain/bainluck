"""Tests for league_classification module."""

import pytest
from app.utils.league_classification import (
    get_league_class,
    is_valid_sport_league_pair,
    is_power_4_team,
    LEAGUE_CLASS,
    POWER_4_TEAMS,
)


class TestGetLeagueClass:
    """Tests for get_league_class()."""

    def test_pro_major(self):
        assert get_league_class("americanfootball_nfl") == "pro_major"
        assert get_league_class("basketball_nba") == "pro_major"
        assert get_league_class("baseball_mlb") == "pro_major"
        assert get_league_class("icehockey_nhl") == "pro_major"
        assert get_league_class("basketball_wnba") == "pro_major"

    def test_college(self):
        assert get_league_class("americanfootball_ncaaf") == "college"
        assert get_league_class("basketball_ncaab") == "college"
        assert get_league_class("basketball_wncaab") == "college"

    def test_pro_minor(self):
        assert get_league_class("americanfootball_cfl") == "pro_minor"
        assert get_league_class("americanfootball_xfl") == "pro_minor"
        assert get_league_class("americanfootball_ufl") == "pro_minor"
        assert get_league_class("icehockey_ahl") == "pro_minor"

    def test_international(self):
        assert get_league_class("soccer_epl") == "international"
        assert get_league_class("soccer_spain_la_liga") == "international"
        assert get_league_class("soccer_usa_mls") == "international"

    def test_unknown_defaults_to_other(self):
        assert get_league_class("unknown_league") == "other"
        assert get_league_class("surfing_wsl") == "other"


class TestSportLeaguePairValidation:
    """Tests for sport/category league consistency guards."""

    def test_valid_pairs(self):
        assert is_valid_sport_league_pair("basketball", "NBA") is True
        assert is_valid_sport_league_pair("football", "NCAAF") is True
        assert is_valid_sport_league_pair("soccer", "UCL") is True
        assert is_valid_sport_league_pair("esports", "LOL") is True

    def test_impossible_pairs(self):
        assert is_valid_sport_league_pair("basketball", "NHL") is False
        assert is_valid_sport_league_pair("hockey", "NBA") is False
        assert is_valid_sport_league_pair("esports", "MLB") is False
        assert is_valid_sport_league_pair("baseball", "VALORANT") is False

    def test_missing_or_unknown_values_are_permissive(self):
        assert is_valid_sport_league_pair("basketball", None) is True
        assert is_valid_sport_league_pair(None, "NBA") is True
        assert is_valid_sport_league_pair("new_sport", "NEW_LEAGUE") is True


class TestIsPower4Team:
    """Tests for is_power_4_team()."""

    def test_sec_teams(self):
        assert is_power_4_team("Alabama") is True
        assert is_power_4_team("Alabama Crimson Tide") is True
        assert is_power_4_team("Texas A&M") is True
        assert is_power_4_team("LSU") is True
        assert is_power_4_team("Vanderbilt") is True

    def test_big_ten_teams(self):
        assert is_power_4_team("Ohio State") is True
        assert is_power_4_team("Ohio State Buckeyes") is True
        assert is_power_4_team("Michigan") is True
        assert is_power_4_team("USC") is True

    def test_big_12_teams(self):
        assert is_power_4_team("BYU") is True
        assert is_power_4_team("UCF") is True
        assert is_power_4_team("TCU") is True

    def test_acc_teams(self):
        assert is_power_4_team("Clemson") is True
        assert is_power_4_team("Duke") is True
        assert is_power_4_team("Notre Dame") is True
        assert is_power_4_team("California Golden Bears") is True
        assert is_power_4_team("Cal Golden Bears") is True
        assert is_power_4_team("SMU") is True

    def test_mid_major_teams(self):
        assert is_power_4_team("Gonzaga") is False
        assert is_power_4_team("Boise State") is False
        assert is_power_4_team("UTEP") is False
        assert is_power_4_team("Coastal Carolina") is False
        assert is_power_4_team("California Baptist") is False
        assert is_power_4_team("Southern California College") is False

    def test_case_insensitive(self):
        assert is_power_4_team("alabama") is True
        assert is_power_4_team("OHIO STATE") is True
        assert is_power_4_team("clemson tigers") is True

    def test_substring_match(self):
        """Power 4 name appearing as substring should match."""
        assert is_power_4_team("Florida Gators") is True
        assert is_power_4_team("North Carolina Tar Heels") is True

    def test_token_boundary_match_avoids_embedded_school_names(self):
        assert is_power_4_team("Northwestern Wildcats") is True
        assert is_power_4_team("Northwestern State Demons") is False
        assert is_power_4_team("Miami Hurricanes") is True
        assert is_power_4_team("Miami OH RedHawks") is False

    def test_empty_and_none(self):
        assert is_power_4_team("") is False
        assert is_power_4_team(None) is False

    def test_power_4_count(self):
        """Verify we have the expected number of Power 4 schools (~67)."""
        assert len(POWER_4_TEAMS) >= 60
        assert len(POWER_4_TEAMS) <= 75
