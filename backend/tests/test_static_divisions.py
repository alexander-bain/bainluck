"""Tests for the static MLB/NFL division map (Queue #242 Item 1c).

The grid division race did not render for MLB/NFL because standings_data is NULL
there; this map is the fallback truth. Cross-league nickname clashes (Cardinals,
Giants, Rangers) must resolve by league scope, and multi-word nicknames
("white sox") must not be shadowed by a shorter suffix.

#6246 re-pinned every expectation in this file: the map now emits the same
labels live standings do ("Central", not "AL Central"; "American Football
Conference", not "AFC"), because `grouped_teams` keys on the raw string and two
spellings of one conference are two blocks on the page. The vocabulary
invariant itself is guarded in `test_playoffs_conference_vocabulary_6246.py`.
"""

from app.utils.static_divisions import lookup_division


class TestMLB:
    def test_full_name_resolves(self):
        assert lookup_division("mlb", "Boston Red Sox") == ("American League", "East")
        assert lookup_division("mlb", "New York Yankees") == ("American League", "East")

    def test_white_sox_not_shadowed_by_red_sox(self):
        assert lookup_division("mlb", "Chicago White Sox") == ("American League", "Central")

    def test_national_league(self):
        assert lookup_division("mlb", "Los Angeles Dodgers") == ("National League", "West")

    def test_sport_key_accepted(self):
        assert lookup_division("baseball_mlb", "Houston Astros") == ("American League", "West")


class TestNFL:
    def test_full_name_resolves(self):
        assert lookup_division("nfl", "Kansas City Chiefs") == ("American Football Conference", "AFC West")
        assert lookup_division("nfl", "Philadelphia Eagles") == ("National Football Conference", "NFC East")

    def test_49ers(self):
        assert lookup_division("nfl", "San Francisco 49ers") == ("National Football Conference", "NFC West")

    def test_sport_key_accepted(self):
        assert lookup_division("americanfootball_nfl", "Buffalo Bills") == ("American Football Conference", "AFC East")


class TestCrossLeagueClashes:
    def test_cardinals_by_league(self):
        # MLB Cardinals (St. Louis) vs NFL Cardinals (Arizona) — league scopes it.
        assert lookup_division("mlb", "St. Louis Cardinals") == ("National League", "Central")
        assert lookup_division("nfl", "Arizona Cardinals") == ("National Football Conference", "NFC West")

    def test_giants_by_league(self):
        assert lookup_division("mlb", "San Francisco Giants") == ("National League", "West")
        assert lookup_division("nfl", "New York Giants") == ("National Football Conference", "NFC East")


class TestMisses:
    def test_unknown_league(self):
        assert lookup_division("nba", "Boston Celtics") == (None, None)

    def test_unknown_team(self):
        assert lookup_division("mlb", "Toronto Raptors") == (None, None)

    def test_empty(self):
        assert lookup_division("", "") == (None, None)
        assert lookup_division("mlb", "") == (None, None)
