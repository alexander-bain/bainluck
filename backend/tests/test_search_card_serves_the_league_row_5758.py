"""#5758 — the front door's club card is the league row, not the spring row.

`/api/teams/boston-red-sox` has served the pennant race since #2498. The CARD the
search page hands the reader is built by `_pick_team_row_per_name` in
`routes/events.py`, which never learned that rule: a season variant and its parent
share a name AND a competition class, so every tie-break in #4489's collapse tied
and the heap order decided which row a reader saw.

Measured on production 2026-09-12 21:3xZ, `/api/events/search?q=red sox` answered

    Boston Red Sox · BASEBALL_MLB_PRESEASON · 13-15

in September, while row 10709 (`baseball_mlb`, 80-68) played the pennant race — and
`yankees` (85-63) and `white sox` (75-72) landed on the league row the same minute.
That is the coin flip these tests convert into a rule. 90 name groups can flip:
32 `americanfootball_nfl_preseason`, 30 `baseball_mlb_preseason`,
28 `basketball_nba_summer_league`, each sharing its name with its own parent.

WHAT THESE TESTS ARE PINNING, beyond the specimen:

* the demotion needs the PARENT IN THE GROUP — a club that only ever appears as a
  variant row is still shown, because a demoted lone row would be a blank card;
* it is keyed on `league_identity`, so a same-name row from a DIFFERENT league can
  never claim to be the parent (measured: 0 of the 90 are cross-league, so this
  arm guards a population that does not exist yet and is the one that would rot
  silently if it did);
* #4489's ordering guarantee is untouched: the survivor takes the first member's
  slot, so a name never moves.
"""

import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _TEAM_COMP_LEAGUE,
    _TEAM_COMP_WOMENS,
    _pick_team_row_per_name,
    _seasons_with_a_parent_row,
    _team_competition_rank,
)


def _body_without_docstring(fn) -> str:
    """The function's STATEMENTS, with its docstring dropped. Pure."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert body, f"{fn.__name__} has no statements outside its docstring"
    return "\n".join(ast.unparse(stmt) for stmt in body)


def _row(name, sport_key, team_id=None, record=None):
    return SimpleNamespace(
        name=name, sport_key=sport_key, id=team_id, current_record=record
    )


def _ids(rows):
    return [r.id for r in rows]


def _keys(rows):
    return [r.sport_key for r in rows]


# The live specimen, both rows, as production held them at 21:3xZ.
_SPRING_RED_SOX = _row("Boston Red Sox", "baseball_mlb_preseason", 853, "13-15")
_LEAGUE_RED_SOX = _row("Boston Red Sox", "baseball_mlb", 10709, "80-68")


# --------------------------------------------------------------------------
# The specimen
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rows,label", [
    ([_SPRING_RED_SOX, _LEAGUE_RED_SOX], "spring row arrives first"),
    ([_LEAGUE_RED_SOX, _SPRING_RED_SOX], "league row arrives first"),
])
def test_red_sox_card_is_the_pennant_race_whichever_row_the_heap_yields(rows, label):
    """The defect was the heap order deciding, so both orders are the test."""
    picked = _pick_team_row_per_name(rows)
    assert _ids(picked) == [10709], label
    assert picked[0].current_record == "80-68", label


@pytest.mark.parametrize("variant,parent", [
    ("baseball_mlb_preseason", "baseball_mlb"),
    ("americanfootball_nfl_preseason", "americanfootball_nfl"),
    ("basketball_nba_summer_league", "basketball_nba"),
])
def test_every_variant_cohort_on_production_defers_to_its_parent(variant, parent):
    """All three variant sports, because all three hold same-name parent rows."""
    picked = _pick_team_row_per_name([
        _row("Club", variant, 1),
        _row("Club", parent, 2),
    ])
    assert _ids(picked) == [2]


# --------------------------------------------------------------------------
# The gate: the demotion needs the parent standing beside it
# --------------------------------------------------------------------------

def test_a_club_that_exists_only_as_a_variant_row_still_shows():
    """A demoted lone row is a blank card, which is worse than a spring record."""
    picked = _pick_team_row_per_name([_SPRING_RED_SOX])
    assert _ids(picked) == [853]


def test_two_variant_rows_with_no_parent_keep_the_incoming_order():
    picked = _pick_team_row_per_name([
        _row("Club", "baseball_mlb_preseason", 1),
        _row("Club", "americanfootball_nfl_preseason", 2),
    ])
    assert _ids(picked) == [1]


def test_a_same_name_row_in_another_league_is_not_a_parent():
    """`league_identity`, not the bare name: an NCAA namesake is another club.

    Measured 2026-09-12: all 90 same-name siblings of a variant row are that
    variant's own parent league, so this arm fires on nothing today. It is the
    one that decides the answer the day a namesake appears, which is exactly when
    nobody will be re-measuring."""
    picked = _pick_team_row_per_name([
        _row("Houston Texans", "americanfootball_nfl_preseason", 1),
        _row("Houston Texans", "americanfootball_ncaaf", 2),
    ])
    assert _ids(picked) == [1]


def test_the_parent_set_is_keyed_on_name_and_league_identity():
    rows = [
        _row("Boston Red Sox", "baseball_mlb", 10709),
        _row("Houston Texans", "americanfootball_ncaaf", 2),
        _row("Ignored", "baseball_mlb_preseason", 853),
    ]
    parents = _seasons_with_a_parent_row(rows)
    assert ("Boston Red Sox", "baseball/mlb") in parents
    # The variant row contributes nothing — it is what the set is consulted for.
    assert not any(name == "Ignored" for name, _ in parents)


# --------------------------------------------------------------------------
# #4489's guarantees, unchanged
# --------------------------------------------------------------------------

def test_ordering_across_names_is_untouched():
    """A name group still occupies its FIRST member's slot (#4489's safety claim)."""
    picked = _pick_team_row_per_name([
        _row("Arsenal", "soccer_epl", 1),
        _SPRING_RED_SOX,
        _row("Chelsea", "soccer_epl", 3),
        _LEAGUE_RED_SOX,
    ])
    assert [r.name for r in picked] == ["Arsenal", "Boston Red Sox", "Chelsea"]
    assert _ids(picked) == [1, 10709, 3]


def test_the_competition_collapse_still_picks_the_clubs_own_league():
    """The soccer rule #4489 shipped is decided before the variant penalty can act."""
    picked = _pick_team_row_per_name([
        _row("Ajax", "soccer_uefa_champs_league_women", 1),
        _row("Ajax", "soccer_netherlands_eredivisie", 2),
    ])
    assert _keys(picked) == ["soccer_netherlands_eredivisie"]


def test_the_variant_penalty_does_not_reclassify_a_competition():
    """`_team_competition_rank` is unchanged: a variant is still its league's class.

    The demotion lives in the collapse, where the group is visible, and NOT in the
    per-row classifier, which cannot see whether the parent is present."""
    assert _team_competition_rank("baseball_mlb_preseason") == _TEAM_COMP_LEAGUE
    assert _team_competition_rank("basketball_nba_summer_league") == _TEAM_COMP_LEAGUE
    assert _team_competition_rank("soccer_germany_bundesliga_women") == _TEAM_COMP_WOMENS


# --------------------------------------------------------------------------
# The rule is derived, not a key list
# --------------------------------------------------------------------------

def test_the_collapse_asks_is_season_variant_rather_than_naming_the_keys():
    """A new variant suffix must inherit this the day `sport_keys` names it.

    `_SEASON_VARIANT_SUFFIXES` is the single source of truth (#4945/#1798); a
    literal `_preseason` in this collapse would be a second one, and the two
    would drift."""
    code = "\n".join(
        _body_without_docstring(fn)
        for fn in (_pick_team_row_per_name, _seasons_with_a_parent_row)
    )
    assert "is_season_variant" in code
    assert "league_identity" in code
    # The docstrings NAME the three keys, which is why the scan reads the body
    # only — a source-scan that its own prose satisfies proves nothing.
    assert "_preseason" not in code
    assert "summer_league" not in code
