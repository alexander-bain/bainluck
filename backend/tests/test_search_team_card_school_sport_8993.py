"""#8993 — searching a school leads with its football row, not whichever sport the heap held.

Production 2026-09-27 00:35Z (CFB Saturday): `/api/events/search?q=notre dame`
served ONE team card, **Notre Dame Fighting Irish · 13-3 · lacrosse_ncaa**
(row 1415), above eight NCAAF games. The football row 835 (4-0) exists. Notre
Dame, Ohio State, Syracuse, Duke and Michigan each hold five same-name rows
(football, men's and women's basketball, baseball, lacrosse), all but the
women's in competition class `_TEAM_COMP_LEAGUE` — so `_pick_team_row_per_name`
fell through to the incoming index and the heap order picked the sport.

The rows below are the production sets for those names, read the same minute,
fed in the heap order that put lacrosse (or basketball) first.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import (
    _college_sport_audience_rank,
    _pick_team_row_per_name,
)


def _row(name, sport_key, team_id):
    return SimpleNamespace(name=name, sport_key=sport_key, id=team_id)


NOTRE_DAME = [
    _row("Notre Dame Fighting Irish", "lacrosse_ncaa", 1415),
    _row("Notre Dame Fighting Irish", "baseball_ncaa", 913),
    _row("Notre Dame Fighting Irish", "basketball_wncaab", 2840),
    _row("Notre Dame Fighting Irish", "basketball_ncaab", 1098),
    _row("Notre Dame Fighting Irish", "americanfootball_ncaaf", 835),
]
OHIO_STATE = [
    _row("Ohio State Buckeyes", "lacrosse_ncaa", 1424),
    _row("Ohio State Buckeyes", "basketball_ncaab", 198),
    _row("Ohio State Buckeyes", "americanfootball_ncaaf", 837),
    _row("Ohio State Buckeyes", "baseball_ncaa", 879),
    _row("Ohio State Buckeyes", "basketball_wncaab", 68),
]


def test_notre_dame_answers_with_football_not_lacrosse():
    picked = _pick_team_row_per_name(NOTRE_DAME)
    assert [(r.id, r.sport_key) for r in picked] == [(835, "americanfootball_ncaaf")]


def test_ohio_state_answers_with_football_not_lacrosse():
    picked = _pick_team_row_per_name(OHIO_STATE)
    assert [r.id for r in picked] == [837]


def test_without_a_football_row_mens_basketball_beats_lacrosse_and_baseball():
    rows = [r for r in NOTRE_DAME if r.sport_key != "americanfootball_ncaaf"]
    assert [r.id for r in _pick_team_row_per_name(rows)] == [1098]


def test_a_womens_row_still_loses_to_every_mens_college_sport():
    """The competition class runs BEFORE the audience rank, so `wncaab` (class
    women's) cannot win on the audience map's 'other college' rank either."""
    rows = [
        _row("Belmont Bruins", "basketball_wncaab", 1),
        _row("Belmont Bruins", "baseball_ncaa", 2),
    ]
    assert [r.id for r in _pick_team_row_per_name(rows)] == [2]


def test_a_college_only_in_a_minor_sport_still_leads_its_own_query():
    rows = [_row("Johns Hopkins Blue Jays", "lacrosse_ncaa", 7)]
    assert [r.id for r in _pick_team_row_per_name(rows)] == [7]


def test_the_school_keeps_its_slot_among_other_names():
    """Position-preserving, as #4489 pins: the group sits where its FIRST member
    sat, whichever row now represents it."""
    rows = [
        _row("Notre Dame College Falcons", "americanfootball_ncaaf", 50),
        *NOTRE_DAME,
        _row("Notre Dame Fighting Irish Women", "soccer_ncaa", 60),
    ]
    assert [r.id for r in _pick_team_row_per_name(rows)] == [50, 835, 60]


@pytest.mark.parametrize("sport_key,expected", [
    ("americanfootball_ncaaf", 0),
    ("basketball_ncaab", 1),
    ("lacrosse_ncaa", 2),
    ("baseball_ncaa", 2),
    ("icehockey_ncaa", 2),
    # Not college: nothing to decide, so a pro or soccer group cannot move.
    ("americanfootball_nfl", 0),
    ("baseball_mlb", 0),
    ("baseball_mlb_preseason", 0),
    ("soccer_epl", 0),
    ("soccer_fa_cup", 0),
    (None, 0),
    ("", 0),
])
def test_the_audience_rank(sport_key, expected):
    assert _college_sport_audience_rank(sport_key) == expected


def test_a_pro_tie_still_keeps_the_incoming_order():
    """The audience rank is 0 for every non-college key, so a tie the
    competition class cannot break is still decided by the incoming order."""
    rows = [
        _row("Hamburger SV", "soccer_germany_bundesliga", 1),
        _row("Hamburger SV", "soccer_germany_bundesliga", 2),
    ]
    assert [r.id for r in _pick_team_row_per_name(rows)] == [1]
