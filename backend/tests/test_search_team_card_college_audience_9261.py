"""#9261 — searching `tigers` cards LSU and Clemson, not Princeton lacrosse.

Production 2026-09-28 01:5xZ, `/search?q=tigers` at 390px: the TEAMS card read
Detroit, Auburn, Grambling State (FCS), Princeton (lacrosse) and Tennessee St
(men's basketball) — no LSU, Clemson, Missouri or Memphis, on a CFB weekend
whose own games list is led by their football games. `bulldogs` put Georgia 4th
behind Butler and Fresno St BASEBALL rows; `wildcats` carded Villanova lacrosse
and no Kentucky.

Cause, read from production's own window (the fixture below is its 25 rows,
verbatim): the scorer ties every `X Tigers` row that owns the alias `Tigers`
(same class, kind and prominence) and falls back to arrival order, which is
`ts_rank_cd`. That rank counts how often the word appears across name +
aliases, so a row that restates its own name as an alias (`Princeton Tigers` on
the lacrosse row, `Grambling Tigers` on the FCS row) scores 4.5 while
`LSU Tigers` scores 3.0. A data artifact was choosing the card.

Fix: the collapsed groups are stably re-sorted by `_college_sport_audience_rank`
(#8993's in-group rule — football, men's basketball, other college) before the
scorer. Non-college rows read 0, so pro and soccer cards cannot move.
"""

import inspect
from types import SimpleNamespace

from app.routes import events as ev
from app.utils.search_match_class import (
    MC0_EXACT,
    MC1_ALL_TOKENS,
    match_class,
)

# (id, name, sport_key, alternate_names, team_rank) — production's `tigers`
# window, 2026-09-28 01:5xZ, compiled from `_team_search_rank` and run through
# db-query in the window's own ORDER BY.
TIGERS_WINDOW = [
    (876, "Auburn Tigers", "baseball_ncaa", ["Auburn Tigers", "Auburn", "Tigers"], 4.5),
    (19779, "Grambling State Tigers", "americanfootball_ncaaf_fcs", ["Grambling Tigers", "Tigers", "Grambling"], 4.5),
    (1410, "Princeton Tigers", "lacrosse_ncaa", ["Tigers", "Princeton", "Princeton Tigers"], 4.5),
    (1158, "Tennessee St Tigers", "basketball_ncaab", ["Tennessee State Tigers", "Tennessee St", "Tigers"], 4.5),
    (3585, "Towson Tigers", "lacrosse_ncaa", ["Towson", "Tigers", "Towson Tigers"], 4.5),
    (10747, "Detroit Tigers", "baseball_mlb", ["Tigers", "Detroit"], 3.0),
    (271, "Auburn Tigers", "basketball_ncaab", ["Tigers", "Auburn"], 3.0),
    (196, "Auburn Tigers", "basketball_wncaab", ["Auburn", "Tigers"], 3.0),
    (7, "Auburn Tigers", "americanfootball_ncaaf", ["Auburn", "Tigers"], 3.0),
    (14667, "Clemson", "baseball_ncaa", ["Tigers", "Clemson Tigers"], 3.0),
    (72, "Clemson Tigers", "basketball_wncaab", ["Tigers", "Clemson"], 3.0),
    (178, "Clemson Tigers", "basketball_ncaab", ["Clemson", "Tigers"], 3.0),
    (4074, "Clemson Tigers", "baseball_ncaa", ["Clemson", "Tigers"], 3.0),
    (10, "Clemson Tigers", "americanfootball_ncaaf", ["Tigers", "Clemson"], 3.0),
    (859, "Detroit Tigers", "baseball_mlb_preseason", ["Tigers", "Detroit"], 3.0),
    (13746, "Grambling Tigers", "baseball_ncaa", ["Tigers", "Grambling"], 3.0),
    (15245, "Jackson State Tigers", "baseball_ncaa", ["Tigers", "Jackson St"], 3.0),
    (18616, "Jackson State Tigers", "americanfootball_ncaaf_fcs", ["Jackson St", "Tigers"], 3.0),
    (265, "LSU Tigers", "basketball_ncaab", ["Tigers", "LSU"], 3.0),
    (70, "LSU Tigers", "basketball_wncaab", ["LSU", "Tigers"], 3.0),
    (900, "LSU Tigers", "baseball_ncaa", ["Tigers", "LSU"], 3.0),
    (9, "LSU Tigers", "americanfootball_ncaaf", ["LSU", "Tigers"], 3.0),
    (15345, "Memphis Tigers", "americanfootball_ncaaf", ["Memphis", "Tigers"], 3.0),
    (2711, "Memphis Tigers", "baseball_ncaa", ["Memphis", "Tigers"], 3.0),
    (13382, "Missouri", "baseball_ncaa", ["Missouri Tigers", "Tigers"], 3.0),
]

# Production's `united` window, same read — no college row in it.
UNITED_WINDOW = [
    (19785, "Manchester United", "soccer_uefa_champs_league", ["Man United"], 3.0),
    (145, "Manchester United", "soccer_epl", ["Man United"], 3.0),
    (14, "Minnesota United FC", "soccer_usa_mls", ["Minnesota", "Minnesota United FC"], 3.0),
    (30, "Atlanta United FC", "soccer_usa_mls", ["Atlanta"], 1.5),
    (31, "D.C. United", "soccer_usa_mls", None, 1.5),
    (1, "Leeds United", "soccer_epl", ["Leeds"], 1.5),
    (15292, "Newcastle", "soccer_epl", ["Newcastle United"], 1.5),
    (2303, "Newcastle United", "soccer_uefa_champs_league", ["Magpies/Toon", "Newcastle"], 1.5),
    (143, "Newcastle United", "soccer_epl", ["Newcastle"], 1.5),
    (15293, "West Ham", "soccer_epl", ["West Ham United"], 1.5),
    (140, "West Ham United", "soccer_epl", ["West Ham"], 1.5),
    (1680, "Adelaide United", "soccer_australia_aleague", None, 1.5),
    (19706, "AFC Telford United", "soccer_fa_cup", None, 1.5),
    (5057, "Akwa United", "soccer_other", None, 1.5),
    (1869, "Cambridge United", "soccer_england_league2", None, 1.5),
    (2235, "Dundee United", "soccer_spl", None, 1.5),
]


def _rows(window):
    return [
        SimpleNamespace(
            id=i, name=name, slug=None, abbreviation=None, logo_url_small=None,
            current_record=None, sport_key=sport_key, standings_updated_at=None,
            alternate_names=aliases, team_rank=rank,
        )
        for i, name, sport_key, aliases, rank in window
    ]


def _card(window, query):
    return [(c["name"], c["sport_key"]) for _k, c in ev._team_card_keyed(_rows(window), query)]


def test_tigers_cards_the_football_schools_behind_detroit():
    assert _card(TIGERS_WINDOW, "tigers") == [
        ("Detroit Tigers", "baseball_mlb"),
        ("Auburn Tigers", "americanfootball_ncaaf"),
        ("Clemson Tigers", "americanfootball_ncaaf"),
        ("LSU Tigers", "americanfootball_ncaaf"),
        ("Memphis Tigers", "americanfootball_ncaaf"),
    ]


def test_strawman_without_the_audience_sort_reproduces_production(monkeypatch):
    """The fixture is the defect: with the sort neutralised, the card is exactly
    what production served (so the test above fails for the right reason)."""
    monkeypatch.setattr(ev, "_college_sport_audience_rank", lambda _key: 0)
    assert [name for name, _ in _card(TIGERS_WINDOW, "tigers")] == [
        "Detroit Tigers", "Auburn Tigers", "Grambling State Tigers",
        "Princeton Tigers", "Tennessee St Tigers",
    ]


def test_control_a_window_with_no_college_row_is_unchanged(monkeypatch):
    after = _card(UNITED_WINDOW, "united")
    monkeypatch.setattr(ev, "_college_sport_audience_rank", lambda _key: 0)
    assert _card(UNITED_WINDOW, "united") == after
    assert after[0] == ("Manchester United", "soccer_epl")


def test_a_better_match_class_still_beats_a_football_row():
    """The re-sort only reorders rows the scorer tied: a lacrosse row that owns the
    exact alias stays above a football row that only carries the word in its name."""
    window = [
        (1410, "Princeton Tigers", "lacrosse_ncaa", ["Tigers", "Princeton"], 3.0),
        (99, "Pacific Tigers", "americanfootball_ncaaf", None, 1.5),
    ]
    rows = _rows(window)
    lacrosse = ev._search_team_evidence({"name": rows[0].name, "_aliases": rows[0].alternate_names, "sport_key": rows[0].sport_key})
    football = ev._search_team_evidence({"name": rows[1].name, "_aliases": [], "sport_key": rows[1].sport_key})
    assert match_class("tigers", lacrosse) == MC0_EXACT
    assert match_class("tigers", football) == MC1_ALL_TOKENS
    assert [name for name, _ in _card(window, "tigers")] == ["Princeton Tigers", "Pacific Tigers"]


def test_prominence_still_beats_a_football_row():
    window = [
        (9, "LSU Tigers", "americanfootball_ncaaf", ["LSU", "Tigers"], 4.5),
        (10747, "Detroit Tigers", "baseball_mlb", ["Tigers", "Detroit"], 3.0),
    ]
    assert [name for name, _ in _card(window, "tigers")][0] == "Detroit Tigers"


def test_the_sort_reads_the_one_audience_rule():
    """One definition with #8993's in-group rule, applied to the collapsed groups."""
    src = inspect.getsource(ev._team_card_keyed)
    assert "key=lambda row: _college_sport_audience_rank(row.sport_key)" in src
    assert ev._college_sport_audience_rank("americanfootball_ncaaf") == 0
    assert ev._college_sport_audience_rank("basketball_ncaab") == 1
    assert ev._college_sport_audience_rank("lacrosse_ncaa") == 2
    assert ev._college_sport_audience_rank("americanfootball_ncaaf_fcs") == 2
    assert ev._college_sport_audience_rank("baseball_mlb") == 0
