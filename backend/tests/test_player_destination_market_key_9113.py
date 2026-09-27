"""#9113 (writer half) — a player's destination market is not its sport's title race.

WHAT THE READER SAW (2026-09-27 ~10:10Z, 390px): LAFC's team page read
CHAMPIONSHIP 1% — Kalshi's "Neymar: Next Club" (market 11372050) keyed
``soccer::championship:2026``. PR #9154 fixed the page; this is the key.

WHY THE KEY MATTERS BEYOND THAT PAGE. ``detect_market_type`` found no
competition in "Steph Curry's Next Team" and returned its "championship"
default, so all 102 open destination markets (Kalshi "X's Next Team",
"X: Next Club"; Polymarket "NBA: Steph Curry Next Team", "Where will Cristiano
Ronaldo go next?") shared their sport's catch-all key:

* Discover's trace of Kalshi-only 12232419 "Steph Curry's Next Team" read
  ``source_count 2`` and reason ``multi_source`` — a Polymarket Turkish-league
  game sits under ``basketball::championship:2026``;
* every player's market was the "same question" as every other's for the
  feed's canonical dedupe; and
* Polymarket's ``basketball:NBA:championship:2026-27`` Steph Curry row matched
  the NBA progression fetch's ``basketball:NBA:championship:%`` pattern.

Counterfactual over every open production name containing "next" (625 names,
2026-09-27 14:15Z): 102 classify as destinations, every one of them a
player's next team, every one previously keyed ``…:championship:…``.
"""

from __future__ import annotations

import fnmatch
import inspect

import pytest

from app.utils.canonical_market_key import canonical_key_identifies_one_question
from app.utils.futures_categorization import (
    compute_canonical_market_key,
    detect_market_type,
    detect_player_destination,
)


# Real production titles (futures_markets.name, open, 2026-09-27) → player slug.
PRODUCTION_DESTINATIONS = [
    ("Neymar: Next Club", "next_team_neymar"),
    ("Steph Curry's Next Team", "next_team_steph_curry"),
    ("NBA: Steph Curry Next Team", "next_team_steph_curry"),
    ("Erling Haaland: Next Club", "next_team_erling_haaland"),
    ("David Alaba: Next Club (League)", "next_team_david_alaba"),
    ("Bronny James' Next Team Before Oct 23, 2026", "next_team_bronny_james"),
    ("Austin Reaves' Next Team", "next_team_austin_reaves"),
    ("J.J. McCarthy Next Team", "next_team_j_j_mccarthy"),
    ("Fernando Tatis Jr.'s Next Team", "next_team_fernando_tatis_jr"),
    ("Kenneth Walker III's next team?", "next_team_kenneth_walker_iii"),
    ("De'Aaron Fox's Next Team", "next_team_de_aaron_fox"),
    ("VALORANT Offseason: Boaster Next Team", "next_team_boaster"),
    ("LoL Offseason: Deft Next Team", "next_team_deft"),
    ("Where will Cristiano Ronaldo go next?", "next_team_cristiano_ronaldo"),
    ("Max Verstappen's Next F1 Team", "next_team_max_verstappen"),
]


@pytest.mark.parametrize("name,expected", PRODUCTION_DESTINATIONS)
def test_a_destination_market_is_typed_by_its_player(name, expected):
    assert detect_player_destination(name) == expected
    assert detect_market_type(name) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        # Still title races.
        ("MLB World Series Winner", "championship"),
        ("Pro Football Champion", "championship"),
        ("2026 Pro Basketball Cup Champion", "championship"),
        ("American League Champion", "al_pennant"),
        # "next … team" that is not a player's move.
        ("Next Team to Score", "championship"),
        ("Next England National Team Head Coach", "championship"),
        ("Golden State Pro Basketball: Next Head Coach", "championship"),
        ("Who will be the next Pope?", "championship"),
    ],
)
def test_non_destination_names_keep_their_type(name, expected):
    assert detect_player_destination(name) is None
    assert detect_market_type(name) == expected


def _key(sport, league, name, season):
    return compute_canonical_market_key(sport, league, detect_market_type(name), season)


def test_neymar_no_longer_keys_as_the_soccer_championship():
    key = _key("soccer", None, "Neymar: Next Club", "2026")
    assert key == "soccer::next_team_neymar:2026"
    assert ":championship:" not in key
    assert key != _key("soccer", None, "Club World Cup Champion", "2026")


def test_two_players_are_two_questions():
    """The feed's canonical dedupe folds same-key cards; two players must not share one."""
    curry = _key("basketball", None, "Steph Curry's Next Team", "2026")
    harden = _key("basketball", None, "James Harden's Next Team", "2026")
    assert curry != harden
    assert canonical_key_identifies_one_question(curry)
    assert canonical_key_identifies_one_question(harden)


def test_polymarket_nba_destination_leaves_the_progression_pattern():
    """routes/futures.py's progression fetch ILIKEs `<sport>:<LEAGUE>:championship:%`."""
    key = _key("basketball", "NBA", "NBA: Steph Curry Next Team", "2026-27")
    assert not fnmatch.fnmatch(key, "basketball:NBA:championship:*")
    # Control: the real title race still matches it.
    title = _key("basketball", "NBA", "NBA Champion", "2026-27")
    assert fnmatch.fnmatch(title, "basketball:NBA:championship:*")


@pytest.mark.parametrize("module_name", ["app.tasks.kalshi", "app.tasks.polymarket"])
def test_both_pollers_type_their_key_through_detect_market_type(module_name):
    """The fix lives in the one function both venue writers call for the key's type."""
    import importlib

    source = inspect.getsource(importlib.import_module(module_name))
    assert "canon_category = detect_market_type(" in source
