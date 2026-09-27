"""#9229 — one club, two spellings, two search cards.

`bainluck.com/search?q=blues` at 390px, production 2026-09-27 23:40Z: the TEAMS
card printed `St Louis Blues 36-33-12 · NHL` (3705) directly above
`St. Louis Blues 1-2-0 · NHL` (571), same crest. `canadiens` printed
`Montréal Canadiens` (3706) above `Montreal Canadiens` (568). The card's
same-club collapse grouped by the EXACT name, so a period or an accent made two
groups, while the team page already reads each pair as one club through
`team_name_fold_key` (#7929).

The rows are the production rows (ids, names, sport keys, standings stamps).
"""

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.routes.events as events_mod
from app.routes.events import _pick_team_row_per_name, _team_card_keyed


def _ts(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _row(team_id, name, sport_key, stamp=None, record=None, rank=0.5):
    return SimpleNamespace(
        id=team_id,
        name=name,
        sport_key=sport_key,
        standings_updated_at=stamp,
        current_record=record,
        slug=f"slug-{team_id}",
        abbreviation=None,
        logo_url_small="https://a.espncdn.com/stl.png",
        alternate_names=[],
        team_rank=rank,
    )


BLUES_3705 = _row(3705, "St Louis Blues", "icehockey_nhl", _ts("2026-09-27T08:00:00"), "36-33-12")
BLUES_571 = _row(571, "St. Louis Blues", "icehockey_nhl", _ts("2026-05-05T08:00:29"), "1-2-0")
HABS_568 = _row(568, "Montreal Canadiens", "icehockey_nhl", _ts("2026-09-27T08:00:00"), "0-0-0")
HABS_3706 = _row(3706, "Montréal Canadiens", "icehockey_nhl", _ts("2026-09-19T08:00:00"), "0-0-0")
HABS_19692 = _row(19692, "Montréal Canadiens", "icehockey_nhl_preseason")


def _ids(rows):
    return [r.id for r in rows]


# --------------------------------------------------------------------------
# The two production specimens
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rows", [
    [BLUES_3705, BLUES_571],
    [BLUES_571, BLUES_3705],
])
def test_the_blues_are_one_card_and_it_is_the_board_written_this_morning(rows):
    assert _ids(_pick_team_row_per_name(rows)) == [3705]


@pytest.mark.parametrize("rows", [
    [HABS_3706, HABS_568, HABS_19692],
    [HABS_568, HABS_3706, HABS_19692],
    [HABS_19692, HABS_3706, HABS_568],
])
def test_the_canadiens_are_one_card_whichever_spelling_arrives_first(rows):
    assert _ids(_pick_team_row_per_name(rows)) == [568]


def test_the_search_card_itself_prints_the_blues_once():
    rows = [
        BLUES_3705,
        BLUES_571,
        _row(572, "Columbus Blue Jackets", "icehockey_nhl", rank=0.3),
    ]
    cards = [card for _key, card in _team_card_keyed(rows, "blues")]
    names = [c["name"] for c in cards]
    assert names.count("St Louis Blues") + names.count("St. Louis Blues") == 1
    blues = next(c for c in cards if "Blues" in c["name"])
    assert (blues["id"], blues["record"]) == (3705, "36-33-12")
    assert "Columbus Blue Jackets" in names


# --------------------------------------------------------------------------
# What the fold must NOT join
# --------------------------------------------------------------------------

def test_fold_alike_names_in_different_leagues_stay_two_cards():
    rows = [
        _row(1, "Djurgårdens IF", "icehockey_sweden_hockey_league", _ts("2026-09-27T00:00:00")),
        _row(2, "Djurgardens IF", "soccer_sweden_allsvenskan", _ts("2026-09-26T00:00:00")),
    ]
    assert _ids(_pick_team_row_per_name(rows)) == [1, 2]


def test_a_reserve_side_is_not_a_spelling_of_its_first_team():
    rows = [
        _row(1, "Portland Timbers", "soccer_usa_mls", _ts("2026-09-20T00:00:00")),
        _row(2, "Portland Timbers 2", "soccer_usa_mls", _ts("2026-09-27T00:00:00")),
    ]
    assert _ids(_pick_team_row_per_name(rows)) == [1, 2]


# --------------------------------------------------------------------------
# What must not move
# --------------------------------------------------------------------------

def test_a_single_spelling_group_still_keeps_arrival_order_not_the_board_age():
    """Same name, same league, different stamps: the pre-#9229 answer (first
    row wins) is unchanged — the board-age term is armed only for a group that
    holds more than one spelling."""
    older_first = [
        _row(1, "Oklahoma State Cowboys", "baseball_ncaa", _ts("2026-05-01T00:00:00")),
        _row(2, "Oklahoma State Cowboys", "baseball_ncaa", _ts("2026-09-27T00:00:00")),
    ]
    assert _ids(_pick_team_row_per_name(older_first)) == [1]


def test_exact_name_groups_across_leagues_still_collapse_as_before():
    rows = [
        _row(1, "Ajax", "soccer_netherlands_eredivisie"),
        _row(2, "Ajax", "soccer_uefa_champs_league_women"),
    ]
    assert _ids(_pick_team_row_per_name(rows)) == [1]


def test_a_merged_group_keeps_its_first_members_slot_and_nothing_else_moves():
    rows = [
        _row(10, "Columbus Blue Jackets", "icehockey_nhl"),
        BLUES_571,
        _row(11, "Toronto Blue Jays", "baseball_mlb"),
        BLUES_3705,
        _row(12, "Johns Hopkins Blue Jays", "lacrosse_ncaa"),
    ]
    assert _ids(_pick_team_row_per_name(rows)) == [10, 3705, 11, 12]


def test_a_row_with_no_board_never_beats_a_spelling_somebody_is_writing():
    rows = [
        _row(1, "St. Louis Blues", "icehockey_nhl", None),
        _row(2, "St Louis Blues", "icehockey_nhl", _ts("2026-01-01T00:00:00")),
    ]
    assert _ids(_pick_team_row_per_name(rows)) == [2]


def test_a_row_without_the_stamp_attribute_is_read_as_no_board():
    """The typeahead's roster rescue selects no stamp column."""
    bare = SimpleNamespace(id=1, name="St. Louis Blues", sport_key="icehockey_nhl")
    rows = [bare, _row(2, "St Louis Blues", "icehockey_nhl", _ts("2026-01-01T00:00:00"))]
    assert _ids(_pick_team_row_per_name(rows)) == [2]


# --------------------------------------------------------------------------
# Wiring: both surfaces SELECT the column the tie-break reads
# --------------------------------------------------------------------------

def test_the_search_and_typeahead_team_selects_carry_the_standings_stamp():
    source = inspect.getsource(events_mod)
    search_stmt = source[source.index("def _search_team_rows_q"):]
    search_stmt = search_stmt[:search_stmt.index(".join(Sport")]
    assert "Team.standings_updated_at" in search_stmt
    typeahead_stmt = source[source.index("    team_query = (\n        select(Team.id"):]
    typeahead_stmt = typeahead_stmt[:typeahead_stmt.index(".join(Sport")]
    assert "Team.standings_updated_at" in typeahead_stmt
