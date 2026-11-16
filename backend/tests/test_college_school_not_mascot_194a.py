"""Ruling 194-A (Alex, Nov 14): a college team's short name is the school, not
the mascot — "Duke", "Gonzaga", "Ole Miss", never "Blue Devils", "Bulldogs",
"Rebels". Professional teams are unchanged.

Every place the server mints a short name of its own is covered here: the
playoff grid's label, the team-progression fallback, the team page's upcoming
games row ("vs Gonzaga · Sat"), and the editorial copy helper. ESPN's
`location` is the school, trusted only when the team's own name starts with it
(on Sun Nov 15 the `stanford-cardinal` row carried `location: "Arkansas"`).
"""

from __future__ import annotations

import inspect

import pytest

from app.utils import team_short_name as tsn


@pytest.mark.parametrize(
    "name,location,expected",
    [
        ("Gonzaga Bulldogs", "Gonzaga", "Gonzaga"),
        ("Ole Miss Rebels", "Ole Miss", "Ole Miss"),
        ("Texas A&M Aggies", "Texas A&M", "Texas A&M"),
        ("Duke Blue Devils", None, "Duke"),  # no location: the mascot is cut
        ("Stanford Cardinal", "Arkansas", "Stanford"),  # a borrowed location is refused
        ("North Carolina Tar Heels", None, "North Carolina"),
        ("Penn Quakers", None, "Penn"),  # every ESPN mascot is known (Nov 16)
        ("Westbrook Zephyrs", None, "Westbrook Zephyrs"),  # unknown mascot: the full name, never a guess
    ],
)
def test_the_school_is_served(name, location, expected):
    assert tsn.school_label(name, location) == expected


@pytest.mark.parametrize(
    "key,college",
    [
        ("basketball_ncaab", True),
        ("basketball_wncaab", True),
        ("americanfootball_ncaaf", True),
        ("basketball_nba", False),
        ("icehockey_nhl", False),
        (None, False),
    ],
)
def test_college_sports_are_recognised(key, college):
    assert tsn.is_college_sport(key) is college


class TestTheGridLabel:
    def test_a_college_team_without_an_abbreviation_serves_its_school(self):
        label = tsn.compact_team_label("Gonzaga Bulldogs", None, sport_key="basketball_ncaab", location="Gonzaga")
        assert label == "Gonzaga"

    def test_the_abbreviation_still_comes_first(self):
        assert tsn.compact_team_label("Duke Blue Devils", "DUKE", sport_key="basketball_ncaab") == "DUKE"

    def test_professional_teams_are_unchanged(self):
        assert tsn.compact_team_label("Dallas Cowboys", None, sport_key="americanfootball_nfl") == "Cowboys"
        assert tsn.compact_team_label("Hull City", None, sport_key="soccer_epl") == "Hull City"

    def test_the_grid_passes_the_sport_and_location(self):
        from app.routes import playoffs

        src = inspect.getsource(playoffs._get_team_metadata)
        assert "sport_key=team.sport.key if team.sport else None" in src
        assert 'location=getattr(team, "location", None)' in src

    def test_the_progression_fallback_never_takes_a_college_mascot(self):
        from app.routes import playoffs

        src = inspect.getsource(playoffs._get_team_progression_for_event_uncached)
        assert "school_label(display_name)" in src and "if is_college_sport(sport_key)" in src


class TestTheTeamPageRows:
    def test_the_opponent_label_is_the_school(self):
        from app.utils.subject_sequence import _extract_short_name

        assert _extract_short_name("Gonzaga Bulldogs", {}, sport="basketball_wncaab") == "Gonzaga"
        assert _extract_short_name("Gonzaga Bulldogs", {"location": "Gonzaga"}, sport="basketball_ncaab") == "Gonzaga"

    def test_a_served_short_name_still_wins_and_pro_teams_are_unchanged(self):
        from app.utils.subject_sequence import _extract_short_name

        assert _extract_short_name("Duke Blue Devils", {"short_name": "Duke"}, sport="basketball_ncaab") == "Duke"
        assert _extract_short_name("Los Angeles Lakers", {}, sport="basketball_nba") == "Lakers"

    def test_the_row_builder_hands_the_card_sport_over(self):
        from app.utils import subject_sequence

        src = inspect.getsource(subject_sequence)
        assert "_extract_short_name(away_name, away_data, sport=card_sport)" in src
        assert "_extract_short_name(home_name, home_data, sport=card_sport)" in src


def test_the_editorial_copy_uses_the_one_mascot_list():
    from app.utils.candidate_editorial_copy import short_team_name

    assert short_team_name("Gonzaga Bulldogs", "basketball_wncaab") == "Gonzaga"
    assert short_team_name("Stanford Cardinal", "basketball_ncaab") == "Stanford"
    assert short_team_name("Dallas Cowboys", "americanfootball_nfl") == "Cowboys"


# ── 194-A on Discover's "closest games tonight" rows (Nov 16) ──
# Monday's first 60 seats, seat 24: "Iona Gaels at UMBC Retrievers: Iona Gaels".
# Neither mascot was on the hand-written list, and the row's team data carries
# no `location`, so the list itself has to know every college mascot.


@pytest.mark.parametrize("name, school", [
    ("Iona Gaels", "Iona"),
    ("UMBC Retrievers", "UMBC"),
    ("Miami (OH) RedHawks", "Miami (OH)"),
    ("Saint Mary's Gaels", "Saint Mary's"),
    ("Boston College Eagles", "Boston College"),
])
def test_every_espn_college_mascot_is_known(name, school):
    assert tsn.school_label(name) == school


def test_no_mascot_is_the_last_word_of_a_school():
    """Stripping a mascot must never cut into a school's own name."""
    from app.config.college_mascots import ESPN_COLLEGE_MASCOTS

    schools = ["Penn State", "Boston College", "Florida Gulf Coast", "Texas A&M",
               "Little Rock", "Loyola Chicago", "Saint Mary's", "North Carolina"]
    for school in schools:
        assert not any(school.lower().endswith(" " + m.lower()) for m in ESPN_COLLEGE_MASCOTS)
        assert tsn.school_label(school) == school


def test_closest_games_rows_print_the_school_for_college_and_change_nothing_for_pro():
    from app.utils.window_events_closest import _extract_blended_leader

    def card(sport, home, away):
        return {"sport": sport, "home_team": home, "away_team": away,
                "hero_probability_source": "blend", "hero_probability": 0.43,
                "hero_probability_away": 0.57, "home_team_data": {"abbreviation": "X"},
                "away_team_data": {"abbreviation": "Y"}}

    _, leader, row, _ = _extract_blended_leader(card("basketball_ncaab", "UMBC Retrievers", "Iona Gaels"))
    assert (leader, row) == ("Iona", "Iona at UMBC: Iona")
    _, leader, row, _ = _extract_blended_leader(card("basketball_nba", "Miami Heat", "Houston Rockets"))
    assert (leader, row) == ("Houston Rockets", "Houston Rockets at Miami Heat: Houston Rockets")
