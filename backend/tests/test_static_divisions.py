"""Tests for the static MLB/NFL division map (Queue #242 Item 1c).

The grid division race did not render for MLB/NFL because standings_data is NULL
there; this map is the fallback truth. Cross-league nickname clashes (Cardinals,
Giants, Rangers) must resolve by league scope, and multi-word nicknames
("white sox") must not be shadowed by a shorter suffix.
"""

from app.utils.static_divisions import lookup_division


class TestMLB:
    def test_full_name_resolves(self):
        assert lookup_division("mlb", "Boston Red Sox") == ("American League", "AL East")
        assert lookup_division("mlb", "New York Yankees") == ("American League", "AL East")

    def test_white_sox_not_shadowed_by_red_sox(self):
        assert lookup_division("mlb", "Chicago White Sox") == ("American League", "AL Central")

    def test_national_league(self):
        assert lookup_division("mlb", "Los Angeles Dodgers") == ("National League", "NL West")

    def test_sport_key_accepted(self):
        assert lookup_division("baseball_mlb", "Houston Astros") == ("American League", "AL West")


class TestNFL:
    def test_full_name_resolves(self):
        assert lookup_division("nfl", "Kansas City Chiefs") == ("AFC", "AFC West")
        assert lookup_division("nfl", "Philadelphia Eagles") == ("NFC", "NFC East")

    def test_49ers(self):
        assert lookup_division("nfl", "San Francisco 49ers") == ("NFC", "NFC West")

    def test_sport_key_accepted(self):
        assert lookup_division("americanfootball_nfl", "Buffalo Bills") == ("AFC", "AFC East")


class TestCrossLeagueClashes:
    def test_cardinals_by_league(self):
        # MLB Cardinals (St. Louis) vs NFL Cardinals (Arizona) — league scopes it.
        assert lookup_division("mlb", "St. Louis Cardinals") == ("National League", "NL Central")
        assert lookup_division("nfl", "Arizona Cardinals") == ("NFC", "NFC West")

    def test_giants_by_league(self):
        assert lookup_division("mlb", "San Francisco Giants") == ("National League", "NL West")
        assert lookup_division("nfl", "New York Giants") == ("NFC", "NFC East")


class TestMisses:
    def test_unknown_league(self):
        assert lookup_division("nba", "Boston Celtics") == (None, None)

    def test_unknown_team(self):
        assert lookup_division("mlb", "Toronto Raptors") == (None, None)

    def test_empty(self):
        assert lookup_division("", "") == (None, None)
        assert lookup_division("mlb", "") == (None, None)
