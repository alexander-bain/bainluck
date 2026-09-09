"""#4489 — the entity card names the club's OWN competition, not the heap's.

`teams` holds one row per competition for a club, which is by design. Nothing
chose between them, so `ajax` answered with "Ajax / UEFA CHAMPS LEAGUE WOMEN" on
both `/api/events/search` and `/api/events/typeahead` — an entity card naming a
competition that appeared nowhere else on the page it headed (the same page's
facet chips read Dutch Eredivisie and UEFA Europa Conference League).

Every tiebreak was a tie: the three Ajax rows share a name, so identical FTS
rank, identical name-ASC, and all three are non-marquee. The answer was the heap
order.

Measured on production 2026-09-09 21:0xZ, four clubs served a women's-competition
row while their men's side existed — `ajax`, `1. FC Köln`, `Eintracht Frankfurt`,
`Leuven` — inside a 27-club women/non-women cohort and a 392-name soccer cohort.
Each of the four is a test below, keyed on its real competition set.

The safety argument, and what these tests are really pinning: the rule fires
ONLY between rows that share a name, and the survivor takes the FIRST member's
slot. So it can change WHICH row represents a name and can never change where
that name sits. `test_ordering_across_names_is_untouched` is the assertion that
carries that claim; if it ever has to be relaxed, the rule has outgrown its
safety argument and needs re-arguing, not re-baselining.
"""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _TEAM_COMP_CONTINENTAL,
    _TEAM_COMP_CUP,
    _TEAM_COMP_LEAGUE,
    _TEAM_COMP_LOWER_LEAGUE,
    _TEAM_COMP_QUALIFICATION,
    _TEAM_COMP_WOMENS,
    _pick_team_row_per_name,
    _team_competition_rank,
)


def _row(name, sport_key, team_id=None):
    return SimpleNamespace(name=name, sport_key=sport_key, id=team_id)


def _keys(rows):
    return [r.sport_key for r in rows]


def _names(rows):
    return [r.name for r in rows]


# --------------------------------------------------------------------------
# The classifier
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sport_key,expected", [
    # The four live specimens' winning rows.
    ("soccer_netherlands_eredivisie", _TEAM_COMP_LEAGUE),
    ("soccer_germany_bundesliga", _TEAM_COMP_LEAGUE),
    ("soccer_belgium_first_div", _TEAM_COMP_LEAGUE),
    ("soccer_epl", _TEAM_COMP_LEAGUE),
    # …and their losing rows.
    ("soccer_uefa_champs_league_women", _TEAM_COMP_WOMENS),
    ("soccer_germany_bundesliga_women", _TEAM_COMP_WOMENS),
    ("soccer_germany_dfb_pokal", _TEAM_COMP_CUP),
    ("soccer_uefa_europa_conference_league", _TEAM_COMP_CONTINENTAL),
    ("soccer_uefa_champs_league", _TEAM_COMP_CONTINENTAL),
    ("soccer_uefa_champs_league_qualification", _TEAM_COMP_QUALIFICATION),
    ("soccer_germany_bundesliga2", _TEAM_COMP_LOWER_LEAGUE),
    ("soccer_efl_champ", _TEAM_COMP_LOWER_LEAGUE),
    ("soccer_fa_cup", _TEAM_COMP_CUP),
    ("soccer_italy_coppa_italia", _TEAM_COMP_CUP),
])
def test_the_classifier_places_each_measured_competition(sport_key, expected):
    assert _team_competition_rank(sport_key) == expected


def test_the_ladder_is_ordered_league_first_womens_last():
    """The integers are free; their RELATIONS are the rule. Pin the relations."""
    assert (
        _TEAM_COMP_LEAGUE
        < _TEAM_COMP_LOWER_LEAGUE
        < _TEAM_COMP_CONTINENTAL
        < _TEAM_COMP_CUP
        < _TEAM_COMP_QUALIFICATION
        < _TEAM_COMP_WOMENS
    )


def test_a_qualification_key_is_not_read_as_its_parent_competition():
    """`soccer_uefa_champs_league_qualification` contains the UCL key as a
    prefix. Substring matching would have classed it continental."""
    assert _team_competition_rank("soccer_uefa_champs_league_qualification") == (
        _TEAM_COMP_QUALIFICATION
    )
    assert _team_competition_rank("soccer_uefa_champs_league") == _TEAM_COMP_CONTINENTAL


def test_an_unknown_key_is_the_entitys_own_competition():
    """The default has to be LEAGUE: a one-row team's competition IS its own,
    and a default of anything else would demote every sport we never listed."""
    assert _team_competition_rank("basketball_nba") == _TEAM_COMP_LEAGUE
    assert _team_competition_rank("cricket_the_hundred") == _TEAM_COMP_LEAGUE
    assert _team_competition_rank(None) == _TEAM_COMP_LEAGUE
    assert _team_competition_rank("") == _TEAM_COMP_LEAGUE


def test_the_womens_marker_is_a_substring_so_a_new_key_inherits_the_rule():
    """A frozenset would have needed editing the day a new women's competition
    arrives. These two are not in any list in the module."""
    assert _team_competition_rank("soccer_spain_liga_f_women") == _TEAM_COMP_WOMENS
    assert _team_competition_rank("basketball_wncaab") == _TEAM_COMP_WOMENS


def test_the_national_team_competitions_are_class_league_on_purpose():
    """A national team's World Cup IS its season, and the World Cup surfacing
    rule downstream keys on a `soccer_fifa_world_cup` row being present in the
    matched list. Demoting them would be a change to that rule by accident."""
    for key in (
        "soccer_fifa_world_cup",
        "soccer_uefa_nations_league",
        "soccer_fifa_world_cup_qualifiers_europe",
    ):
        assert _team_competition_rank(key) == _TEAM_COMP_LEAGUE


# --------------------------------------------------------------------------
# The four live specimens
# --------------------------------------------------------------------------

def test_ajax_answers_with_the_eredivisie_not_the_womens_champions_league():
    """Production, 2026-09-09: team ids 2141 / 18404 / 19026, served in the
    order below, and the card read "UEFA CHAMPS LEAGUE WOMEN"."""
    rows = [
        _row("Ajax", "soccer_uefa_champs_league_women", 18404),
        _row("Ajax", "soccer_netherlands_eredivisie", 2141),
        _row("Ajax", "soccer_uefa_europa_conference_league", 19026),
    ]
    picked = _pick_team_row_per_name(rows)
    assert len(picked) == 1
    assert picked[0].sport_key == "soccer_netherlands_eredivisie"
    assert picked[0].id == 2141


def test_koln_answers_with_the_bundesliga_not_the_womens_bundesliga():
    rows = [
        _row("1. FC Köln", "soccer_germany_bundesliga_women"),
        _row("1. FC Köln", "soccer_germany_bundesliga"),
        _row("1. FC Köln", "soccer_germany_dfb_pokal"),
    ]
    assert _keys(_pick_team_row_per_name(rows)) == ["soccer_germany_bundesliga"]


def test_eintracht_frankfurt_answers_with_the_bundesliga():
    """Two of this club's three rows are women's competitions, and one of them
    is first. The cup/continental ladder alone would not have saved it."""
    rows = [
        _row("Eintracht Frankfurt", "soccer_germany_bundesliga_women"),
        _row("Eintracht Frankfurt", "soccer_uefa_champs_league_women"),
        _row("Eintracht Frankfurt", "soccer_germany_bundesliga"),
    ]
    assert _keys(_pick_team_row_per_name(rows)) == ["soccer_germany_bundesliga"]


def test_leuven_answers_with_the_belgian_first_division():
    rows = [
        _row("Leuven", "soccer_uefa_champs_league_women"),
        _row("Leuven", "soccer_belgium_first_div"),
    ]
    assert _keys(_pick_team_row_per_name(rows)) == ["soccer_belgium_first_div"]


def test_arsenal_answers_with_the_premier_league_not_a_cup_or_europe():
    """Arsenal holds five rows. Both EPL and UCL are marquee keys, so the
    existing marquee tiebreak is a tie here too."""
    rows = [
        _row("Arsenal", "soccer_uefa_champs_league"),
        _row("Arsenal", "soccer_england_efl_cup"),
        _row("Arsenal", "soccer_fa_cup"),
        _row("Arsenal", "soccer_epl"),
        _row("Arsenal", "soccer_uefa_champs_league_women"),
    ]
    assert _keys(_pick_team_row_per_name(rows)) == ["soccer_epl"]


# --------------------------------------------------------------------------
# The safety argument
# --------------------------------------------------------------------------

def test_a_womens_only_club_still_leads_its_own_query():
    """The rule is a tiebreak among SAME-NAME rows, so a club with no men's row
    has no competitor and is untouched — it must not be filtered, demoted, or
    lose its slot to a differently-named row."""
    rows = [
        _row("Wolfsburg Frauen", "soccer_germany_bundesliga_women"),
        _row("Some Other Club", "soccer_germany_bundesliga"),
    ]
    picked = _pick_team_row_per_name(rows)
    assert _names(picked) == ["Wolfsburg Frauen", "Some Other Club"]
    assert picked[0].sport_key == "soccer_germany_bundesliga_women"


def test_ordering_across_names_is_untouched():
    """THE safety assertion. A name group takes the slot of its FIRST member, so
    a better-classed row can never lift its NAME up the list. Here the women's
    Ajax row arrives first and the Eredivisie row arrives last of all; Ajax must
    still sit where the women's row sat, at index 0."""
    rows = [
        _row("Ajax", "soccer_uefa_champs_league_women"),
        _row("Feyenoord", "soccer_netherlands_eredivisie"),
        _row("PSV Eindhoven", "soccer_uefa_champs_league"),
        _row("Ajax", "soccer_netherlands_eredivisie"),
    ]
    picked = _pick_team_row_per_name(rows)
    assert _names(picked) == ["Ajax", "Feyenoord", "PSV Eindhoven"]
    assert picked[0].sport_key == "soccer_netherlands_eredivisie"


def test_rows_with_no_same_name_sibling_are_byte_for_byte_the_old_behaviour():
    """Nothing shares a name, so every class comparison is between groups of
    one and the function is the identity — including for a cup row and a
    women's row, which the ladder would sink if it ever ran across names."""
    rows = [
        _row("Chelsea", "soccer_fa_cup"),
        _row("Barcelona SC", "soccer_epl"),
        _row("Wolfsburg Frauen", "soccer_uefa_champs_league_women"),
        _row("Sparta Prague", "soccer_uefa_champs_league_qualification"),
    ]
    picked = _pick_team_row_per_name(rows)
    assert picked == rows


def test_a_tie_inside_one_class_keeps_the_incoming_order():
    """The surface that fed us already ordered its rows (FTS rank, then the
    marquee tiebreak). When the competition class cannot separate two rows, that
    order is the last word — this function never re-decides it."""
    rows = [
        _row("Hamburger SV", "soccer_germany_bundesliga", 1),
        _row("Hamburger SV", "soccer_germany_bundesliga", 2),
    ]
    assert [r.id for r in _pick_team_row_per_name(rows)] == [1]


def test_an_empty_list_is_an_empty_list():
    assert _pick_team_row_per_name([]) == []


def test_rows_missing_the_attributes_do_not_raise():
    """Both call sites pass SQLAlchemy Row objects, but the search surface has
    already been observed handing this family of helpers rows built elsewhere.
    Degrade to one group, never to a 500."""
    rows = [SimpleNamespace(), SimpleNamespace()]
    assert len(_pick_team_row_per_name(rows)) == 1


# --------------------------------------------------------------------------
# Reach — a pure function proves the SHAPE of a rule and nothing about whether
# any surface runs it. Both surfaces reproduced the bug, so both must call it.
# --------------------------------------------------------------------------

def _events_module_tree():
    source = Path(inspect.getsourcefile(_pick_team_row_per_name)).read_text()
    return ast.parse(source)


def _function_named(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _calls_within(node):
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }


@pytest.mark.parametrize("route_function", ["search_events", "typeahead_search"])
def test_both_reproducing_surfaces_actually_call_the_picker(route_function):
    tree = _events_module_tree()
    node = _function_named(tree, route_function)
    assert node is not None, (
        f"{route_function} is gone or renamed — this guard is now blind, which is "
        "the failure mode it exists to prevent. Re-point it, do not delete it."
    )
    assert "_pick_team_row_per_name" in _calls_within(node), (
        f"{route_function} no longer calls _pick_team_row_per_name. #4489 was "
        "reproduced on BOTH the search team card and the typeahead dropdown; a "
        "fix wired to one of them leaves the other serving the women's row."
    )


def test_no_surface_still_uses_the_first_writer_wins_collapse():
    """The defect was a `seen`-set collapse keeping whichever row arrived first.
    Two of the three `teams_seen` sites were converted; the third is the trigram
    fuzzy fallback, which appends to an already-collapsed pool. If a new
    first-writer-wins team collapse appears, this guard is the place it is
    caught — the count is the assertion."""
    source = Path(inspect.getsourcefile(_pick_team_row_per_name)).read_text()
    assert source.count("teams_seen.add(") == 2, (
        "The number of first-writer-wins team collapses changed. Read WHICH "
        "way before touching this number: a new one is the #4489 defect coming "
        "back on a third surface; a removed one wants this number lowered."
    )
