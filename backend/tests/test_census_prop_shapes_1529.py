"""#1529 — the census counts soccer and NHL props as props, not as "other".

THE AFTER-CHECK FINDING (issue comment 6130905860). The 30-day capture census
on main v5675 (`scripts/capture_census.py --phase a`, run.5600) breached the
10% `other` ceiling on three core sports — NHL 10.2%, La Liga 21.0%, MLS 33.1%
— and the shared classifier, run locally on a 1,000-row sample per sport, said
why: the bucket was genuine props the vocabularies did not know.

    "Lyle Foster: 3+ goals"                         (Polymarket)  -> other
    "Ángel Pérez: 2+ shots on target"               (Polymarket)  -> other
    "St. Louis vs Chicago: Goals"   KXNHLGOAL-…     (outcomes "Adam Jiricek: 1+")
    "St. Louis vs Chicago: First Goalscorer"        KXNHLFIRSTGOAL-…
    "Montreal vs Toronto: Overtime"                 KXNHLOT-…
    "FC Cincinnati vs Charlotte FC: Correct Score"  KXMLSSCORE-…

The new arms sit at the very end of `classify_game_market_class`, so they are
read only for a title that would otherwise be `other`. That is the whole safety
argument — no answer already given moves, nothing crosses `moneyline` (the five
consumers that key on it) and nothing enters the refresh-budgeted
`spread`/`total` — and `test_only_an_other_answer_moves` proves it by running
the corpus with the arms switched off.
"""

from __future__ import annotations

import re

import pytest

from app.utils import capture_census as cc
from app.utils import game_market_class as gmc
from app.utils.game_market_class import classify_game_market_class

HEX = "0x72b75a4f7fe582bd0898cad3c4f3f5a8992f33ed412"

#: (name, external_id, sport, expected) — every row a production title.
MOVED = [
    ("Lyle Foster: 3+ goals", HEX, "soccer_usa_mls", "player_prop"),
    ("Kelvin Yeboah: 2+ goals", HEX, "soccer_usa_mls", "player_prop"),
    ("Vladyslav Babohlo: 5+ shots", HEX, "soccer_uefa_nations_league", "player_prop"),
    ("Vladyslav Babohlo: 4+ shots on target", HEX, "soccer_uefa_nations_league",
     "player_prop"),
    ("Will Cristian Roldan be in Seattle Sounders FC's Starting 11?", HEX,
     "soccer_usa_mls", "player_prop"),
    ("St. Louis vs Chicago: Goals", "KXNHLGOAL-26OCT06STLCHI", "icehockey_nhl",
     "player_prop"),
    ("St. Louis vs Chicago: First Goalscorer", "KXNHLFIRSTGOAL-26OCT06STLCHI",
     "icehockey_nhl", "player_prop"),
    ("Arsenal vs Chelsea: First Goalscorer", "KXEPLFIRSTGOAL-26OCT04ARSCHE",
     "soccer_epl", "player_prop"),
    ("Montreal vs Toronto: Overtime", "KXNHLOT-26SEP29MTLTOR", "icehockey_nhl",
     "team_prop"),
    ("Ohio State vs Michigan: Overtime", "KXNCAAFOT-26NOV28OSUMICH",
     "americanfootball_ncaaf", "team_prop"),
    ("Montreal vs Toronto: Goal in First 10 Minutes", "KXNHLF10G-26SEP29MTLTOR",
     "icehockey_nhl", "team_prop"),
    ("FC Cincinnati vs Charlotte FC: Correct Score", "KXMLSSCORE-26SEP12CINCLT",
     "soccer_usa_mls", "team_prop"),
    ("Seattle Sounders FC vs. Sporting Kansas City - Exact Score", "1043682",
     "soccer_usa_mls", "team_prop"),
    ("Getafe vs Malaga: Team Corners", "KXLALIGATCORNERS-26SEP20GETMCF",
     "soccer_spain_la_liga", "team_prop"),
    ("Getafe vs Malaga: Total Corners", "KXLALIGACORNERS-26SEP20GETMCF",
     "soccer_spain_la_liga", "team_prop"),
    ("Deportivo Alavés vs. Valencia CF - Total Corners", "952241",
     "soccer_spain_la_liga", "team_prop"),
]

#: Titles that carry a new token but are already answered upstream, plus the
#: shapes that must stay "other". None of these may change.
UNMOVED = [
    # moneyline controls: the boundary five consumers key on
    ("Montreal vs Toronto", "KXNHLGAME-26SEP29MTLTOR", "icehockey_nhl", "moneyline"),
    ("FC Cincinnati vs Charlotte FC", "KXMLSGAME-26SEP12CINCLT", "soccer_usa_mls",
     "moneyline"),
    # already a total / spread: must not leak OUT of the refresh-budgeted classes
    ("Seattle Sounders FC vs. Sporting Kansas City: O/U 2.5", HEX, "soccer_usa_mls",
     "total"),
    ("Total Corners: O/U 9.5", HEX, "soccer_epl", "total"),
    ("Arsenal vs Chelsea: Total Goals", "KXEPLTOTAL-26OCT04ARSCHE", "soccer_epl",
     "total"),
    # already a prop upstream
    ("Lyle Foster: Anytime Goalscorer", HEX, "soccer_usa_mls", "player_prop"),
    ("Arsenal vs Chelsea: Both Teams to Score", HEX, "soccer_epl", "team_prop"),
    # containers and an unanchored "Goals" tail stay "other"
    ("Chicago White Sox vs. Cleveland Guardians - Player Props", HEX, "baseball_mlb",
     "other"),
    ("Levante UD vs. FC Barcelona - More Markets", HEX, "soccer_spain_la_liga",
     "other"),
    ("St. Louis vs Chicago: Goals", HEX, "icehockey_nhl", "other"),
    ("St. Louis vs Chicago: Goals", None, "icehockey_nhl", "other"),
]


@pytest.mark.parametrize("name,ext,sport,expected", MOVED)
def test_the_census_specimens_are_props(name, ext, sport, expected):
    assert classify_game_market_class(name, ext, sport) == expected


@pytest.mark.parametrize("name,ext,sport,expected", UNMOVED)
def test_the_controls_keep_their_answer(name, ext, sport, expected):
    assert classify_game_market_class(name, ext, sport) == expected


_NEVER = re.compile(r"(?!)")


def test_only_an_other_answer_moves(monkeypatch):
    """Switch the new arms off: every difference must be other -> a prop."""
    on = {(n, e, s): classify_game_market_class(n, e, s) for n, e, s, _ in MOVED + UNMOVED}
    for attr in ("_PLAYER_PROP_TAIL_RE", "_KALSHI_GOALS_TAIL_RE", "_GAME_PROP_TAIL_RE"):
        monkeypatch.setattr(gmc, attr, _NEVER)
    off = {k: classify_game_market_class(*k) for k in on}
    moved = {k: (off[k], on[k]) for k in on if off[k] != on[k]}
    assert {k for k in moved} == {(n, e, s) for n, e, s, _ in MOVED}, moved
    for before, after in moved.values():
        assert before == "other" and after in ("player_prop", "team_prop")


def test_the_census_takes_them_out_of_other_and_keeps_the_denominator():
    rows = [(s, n, e, 2, 0, 0, 0, 0) for n, e, s, _ in MOVED if s == "soccer_usa_mls"]
    rows.append(("soccer_usa_mls", "FC Cincinnati vs Charlotte FC",
                 "KXMLSGAME-26SEP12CINCLT", 3, 0, 0, 0, 0))
    by_sc, other_names = cc.tally_market_rows(rows)
    mls = by_sc["soccer_usa_mls"]
    assert "other" not in mls and "soccer_usa_mls" not in other_names
    assert sum(mc.markets for mc in mls.values()) == len(rows)
    assert mls["moneyline"].markets == 1
    assert mls["player_prop"].markets == 3 and mls["team_prop"].markets == 2
