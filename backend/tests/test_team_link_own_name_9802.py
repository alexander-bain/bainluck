"""#9802 — a club's full name binds to the row NAMED for it, not to nothing.

WHAT A READER SAW. The Maple Leafs', Blues' and Canadiens' team pages had no
Championship path card (the Bruins' page shows "Win Conference 2% → Win
Championship 1%"). Measured 2026-09-30: every open, unlinked leg on Kalshi's
NHL Stanley Cup, conference, playoff and Presidents' Trophy boards belonged to
one of five clubs — Columbus, Montréal, Ottawa, St. Louis, Toronto.

WHY. Each of those clubs has a second, city-only ``icehockey_nhl`` row that
lists the full name as an alias (12715 "Toronto" → ["Maple Leafs", "Toronto
Maple Leafs"]). ``match_outcome_to_league_team`` needs exactly one exact hit,
so "Toronto Maple Leafs" hit 115 AND 12715 and bound nothing.

The rows below are production's own (id, name, ``alternate_names``), read from
``teams`` on 2026-09-30.
"""

from __future__ import annotations

from app.utils.team_linking import match_outcome_to_league_team


def _t(team_id, name, alts):
    return {"id": team_id, "name": name, "alternate_names": alts, "sport_key": "icehockey_nhl"}


LEAFS = _t(115, "Toronto Maple Leafs", ["Maple Leafs"])
TORONTO = _t(12715, "Toronto", ["Maple Leafs", "Toronto Maple Leafs"])
BLUES = _t(571, "St. Louis Blues", ["Blues", "St. Louis"])
BLUES_NODOT = _t(3705, "St Louis Blues", ["St. Louis Blues", "St. Louis", "Blues"])
ST_LOUIS = _t(6775, "St. Louis", ["St. Louis Blues", "Blues"])
HABS = _t(568, "Montreal Canadiens", ["Canadiens", "Montreal", "habs"])
HABS_ACCENT = _t(3706, "Montréal Canadiens", ["Canadiens", "Montreal Canadiens"])
MONTREAL = _t(12651, "Montreal", ["Montreal Canadiens", "Canadiens"])
SENS = _t(56, "Ottawa Senators", ["Senators", "sens"])
OTTAWA = _t(13381, "Ottawa", ["Ottawa Senators", "Senators"])
CBJ = _t(572, "Columbus Blue Jackets", ["Columbus", "Blue Jackets"])
COLUMBUS = _t(6182, "Columbus", ["Columbus Blue Jackets", "Blue Jackets"])
BRUINS = _t(574, "Boston Bruins", ["Bruins", "Boston"])
KRAKEN = _t(117, "Seattle Kraken", ["Kraken", "Seattle"])

NHL = [
    LEAFS, TORONTO, BLUES, BLUES_NODOT, ST_LOUIS, HABS, HABS_ACCENT, MONTREAL,
    SENS, OTTAWA, CBJ, COLUMBUS, BRUINS, KRAKEN,
]


def test_full_name_binds_to_the_row_named_for_the_club():
    assert match_outcome_to_league_team("Toronto Maple Leafs", NHL) == 115
    assert match_outcome_to_league_team("Ottawa Senators", NHL) == 56
    assert match_outcome_to_league_team("Columbus Blue Jackets", NHL) == 572


def test_rows_that_spell_one_club_alike_are_one_club():
    """571/3705 and 568/3706 differ only by a dot or an accent — the fold key the
    team page joins a club's rows by (#7929) — so Kalshi's spellings land on the
    lowest id, which is the row the club's URL serves."""
    assert match_outcome_to_league_team("St. Louis Blues", NHL) == 571
    assert match_outcome_to_league_team("Montréal Canadiens", NHL) == 568
    assert match_outcome_to_league_team("Montreal Canadiens", NHL) == 568


def test_a_city_alone_still_names_no_one():
    """"Toronto" is 12715's own name, but it is a shortening of 115's: binding it
    to the city-only row would put the leg where no club page reads it."""
    for city in ("Toronto", "St. Louis", "Montreal", "Ottawa", "Columbus"):
        assert match_outcome_to_league_team(city, NHL) is None, city


def test_an_alias_that_is_another_teams_name_does_not_win():
    """#8353's shape: a row listing another school's name as an alias."""
    michigan = _t(1, "Michigan Wolverines", ["Wolverines", "Michigan"])
    akron = _t(2, "Akron Zips", ["Michigan Wolverines", "Akron", "Zips"])
    assert match_outcome_to_league_team("Michigan Wolverines", [michigan, akron]) == 1


def test_two_different_clubs_with_the_name_as_alias_stay_ambiguous():
    """No row is NAMED for the outcome: the tiebreak has nothing to prefer."""
    a = _t(1, "Toronto", ["Toronto Maple Leafs"])
    b = _t(2, "Leafs", ["Toronto Maple Leafs"])
    assert match_outcome_to_league_team("Toronto Maple Leafs", [a, b]) is None


def test_a_longer_sibling_name_still_shadows():
    """A row named "Toronto Maple Leafs Alumni" makes the outcome a shortening
    of another team's name: refused, as the exact arm always refused."""
    alumni = _t(9, "Toronto Maple Leafs Alumni", ["Leafs Alumni"])
    assert match_outcome_to_league_team("Toronto Maple Leafs", [LEAFS, TORONTO, alumni]) is None


def test_single_row_clubs_are_unchanged():
    assert match_outcome_to_league_team("Boston Bruins", NHL) == 574
    assert match_outcome_to_league_team("Seattle Kraken", NHL) == 117
