"""#9439 — search must print one award race once, not once per venue.

`bainluck.com` at 390px (production `d3d1cc79`, 2026-09-28 ~18:40Z): typing
`mvp` showed Kalshi 40532 `MVP Winner?` (Josh Allen 25%) and Polymarket 7585490
`Pro Football: 2026 MVP Winner` (Josh Allen 22%); `cy young` showed Kalshi 219
`AL Cy Young Winner?` and Polymarket 132810 `MLB: 2026 AL Cy Young Winner`.
The fixtures are those production rows: id, source, name, tier, resolution date
and the first eight listed names in probability order (db-query, 18:5xZ).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.routes import events as events_route
from app.utils.market_label_normalization import (
    get_merge_group,
    get_whole_label_merge_group,
    normalize_market_label,
)


class _Outcome:
    def __init__(self, name):
        self.name = name


class _Market:
    def __init__(self, id, source, name, market_tier, resolution, names=()):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.canonical_market_key = None
        self.resolution_date = resolution
        self.outcomes = [_Outcome(n) for n in names]


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


KALSHI_NFL_MVP = _Market(
    40532, "kalshi", "MVP Winner?", 3, _utc(2027, 3, 14, 15),
    ["Josh Allen", "Brock Purdy", "Lamar Jackson", "Patrick Mahomes",
     "Joe Burrow", "Trevor Lawrence", "Jalen Hurts", "Tyler Shough"],
)
POLY_NFL_MVP = _Market(
    7585490, "polymarket", "Pro Football: 2026 MVP Winner", 3, _utc(2027, 3, 1, 4, 59),
    ["Josh Allen", "Lamar Jackson", "Brock Purdy", "Patrick Mahomes",
     "Joe Burrow", "Trevor Lawrence", "Caleb Williams", "Jalen Hurts"],
)
KALSHI_NBA_MVP = _Market(
    52755650, "kalshi", "Pro Basketball MVP Winner", 3, _utc(2027, 7, 31, 14),
    ["Victor Wembanyama", "Luka Doncic", "Shai Gilgeous-Alexander", "Nikola Jokić",
     "Jayson Tatum", "Giannis Antetokounmpo", "Anthony Edwards", "Jalen Brunson"],
)
KALSHI_AL_CY = _Market(
    219, "kalshi", "AL Cy Young Winner?", 3, _utc(2026, 12, 8, 15),
    ["Cam Schlittler", "Garrett Crochet", "Cole Ragans", "Bryan Woo",
     "George Kirby", "Kevin Gausman", "Ranger Suarez", "Trevor Rogers"],
)
POLY_AL_CY = _Market(
    132810, "polymarket", "MLB: 2026 AL Cy Young Winner", 3, _utc(2027, 1, 1, 4, 59),
    ["Cam Schlittler", "Dylan Cease", "Tarik Skubal", "Sonny Gray",
     "Jacob deGrom", "Drew Rasmussen", "Pablo Lopez", "Kevin Gausman",
     "Garrett Crochet"],
)
KALSHI_AL_MVP = _Market(
    216, "kalshi", "AL MVP Winner?", 3, _utc(2026, 12, 8, 15),
    ["Yordan Álvarez", "Cam Schlittler", "Junior Caminero", "Aaron Judge",
     "Bobby Witt Jr.", "Cal Raleigh", "Gunnar Henderson", "Garrett Crochet",
     "Kevin Gausman"],
)


def _admit(rows):
    seen, by_q, boards = set(), {}, []
    return [m.id for m in rows if events_route._admit_search_future(m, seen, by_q, boards)]


# ── the specimens ───────────────────────────────────────────────────────


def test_mvp_prints_the_nfl_race_once():
    """The reader's `mvp`, in served rank order: Kalshi NFL, Kalshi NBA, Polymarket NFL."""
    assert _admit([KALSHI_NFL_MVP, KALSHI_NBA_MVP, POLY_NFL_MVP]) == [40532, 52755650]


def test_cy_young_prints_the_al_race_once():
    assert _admit([KALSHI_AL_CY, POLY_AL_CY]) == [219]


def test_the_ranked_leader_survives_whichever_venue_it_is():
    assert _admit([POLY_AL_CY, KALSHI_AL_CY]) == [132810]


def test_the_pair_is_refused_by_every_earlier_rule():
    """Anti-vacuity: without the new arm the pair really is two rows."""
    seen, by_q, boards = set(), {}, []
    assert events_route._admit_search_future(KALSHI_AL_CY, seen, by_q, boards)
    assert not events_route._is_repeat_of_a_kept_question(POLY_AL_CY, by_q)
    assert not events_route._is_paraphrase_of_a_kept_board(POLY_AL_CY, boards)
    assert events_route._is_same_award_race_as_a_kept_board(POLY_AL_CY, boards)


# ── controls: stay two rows ─────────────────────────────────────────────


def test_nfl_and_nba_mvp_share_a_group_but_not_a_field():
    """Both clean to `MVP` → group `mvp`; the field gate is what keeps them apart."""
    assert _search_race(KALSHI_NBA_MVP) == _search_race(POLY_NFL_MVP) == "mvp"
    assert _admit([KALSHI_NBA_MVP, POLY_NFL_MVP]) == [52755650, 7585490]


def test_two_leagues_mvp_inside_one_season_window_are_kept_apart_by_the_field():
    """The `mvp` rule is league-blind (`^(?:NBA|NHL|MLB|NFL|MLS)?MVP$`). NBA's
    board above also misses the NFL window, so this constructed MLS board sits
    89 days from Kalshi's NFL race: only the field gate refuses it."""
    mls = _Market(5, "polymarket", "MLS MVP Winner", 3, _utc(2026, 12, 15),
                  ["Lionel Messi", "Sam Surridge", "Denis Bouanga", "Anders Dreyer"])
    assert _search_race(mls) == _search_race(KALSHI_NFL_MVP) == "mvp"
    assert _admit([KALSHI_NFL_MVP, mls]) == [40532, 5]


def test_al_mvp_and_al_cy_young_share_names_but_are_two_races():
    assert _admit([KALSHI_AL_MVP, POLY_AL_CY]) == [216, 132810]


def test_next_seasons_board_is_not_this_seasons():
    nxt = _Market(
        1, "polymarket", "MLB: 2027 AL Cy Young Winner", 3, _utc(2028, 1, 1, 4, 59),
        [o.name for o in POLY_AL_CY.outcomes],
    )
    assert _admit([KALSHI_AL_CY, nxt]) == [219, 1]


def test_two_named_years_must_agree_even_inside_the_window():
    other = _Market(
        2, "kalshi", "2027 AL Cy Young Winner?", 3, _utc(2026, 12, 20),
        [o.name for o in KALSHI_AL_CY.outcomes],
    )
    assert _admit([POLY_AL_CY, other]) == [132810, 2]


def test_a_board_with_no_resolution_date_never_folds():
    undated = _Market(3, "odds_api", "MLB: AL Cy Young", 3, None,
                      [o.name for o in POLY_AL_CY.outcomes])
    assert _admit([KALSHI_AL_CY, undated]) == [219, 3]


def test_same_venue_pair_is_left_to_the_tiered_key():
    twin = _Market(4, "kalshi", "MLB: 2026 AL Cy Young Winner", 2, _utc(2026, 12, 8, 15),
                   [o.name for o in KALSHI_AL_CY.outcomes])
    assert _admit([KALSHI_AL_CY, twin]) == [219, 4]


# ── the whole-label gate ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name, loose_group",
    [
        ("Pro Football: Team to advance to NFC Championship Game", "nfc_champion"),
        ("AFC Champions League Elite 2026-27 Winner", "afc_champion"),
        ("Women's Pro Basketball Champion", "nba_champion"),
        ("Tampa Bay vs Pittsburgh: Head-to-Head Win Total", "win_total"),
    ],
)
def test_a_group_matched_inside_the_label_is_not_a_race(name, loose_group):
    """Production rows (2026-09-28) the rail's key puts in a title race's group."""
    clean = normalize_market_label(name)
    assert get_merge_group(clean) == loose_group
    assert get_whole_label_merge_group(clean) is None


@pytest.mark.parametrize(
    "name, group",
    [
        ("AL Cy Young Winner?", "al_cy_young"),
        ("MLB: 2026 AL Cy Young Winner", "al_cy_young"),
        ("MLB: 2026 NL MVP", "nl_mvp"),
        ("Pro Football: 2026 MVP Winner", "mvp"),
        ("MLB: 2026 American League Champion", "al_champion"),
        ("NHL Vezina Trophy Winner", "vezina_trophy"),
    ],
)
def test_whole_label_group_agrees_with_the_rail_when_it_answers(name, group):
    clean = normalize_market_label(name)
    assert get_whole_label_merge_group(clean) == get_merge_group(clean) == group


def test_nfc_title_race_and_reaching_the_title_game_stay_two_rows_on_one_field():
    """The same four names on both boards, so only the whole-label gate refuses it."""
    names = ["Los Angeles Rams", "Dallas Cowboys", "Seattle Seahawks", "Philadelphia Eagles"]
    win = _Market(31615, "kalshi", "NFC Championship Winner", 2, _utc(2027, 2, 8, 15), names)
    reach = _Market(60087221, "polymarket",
                    "Pro Football: Team to advance to NFC Championship Game", 2,
                    _utc(2027, 1, 26, 23, 59), names)
    assert _admit([win, reach]) == [31615, 60087221]


# ── wiring ──────────────────────────────────────────────────────────────


def test_admit_asks_the_award_arm():
    src = inspect.getsource(events_route._admit_search_future)
    assert "_is_same_award_race_as_a_kept_board(market, kept_boards)" in src


def _search_race(m):
    return events_route._search_award_race(m)
