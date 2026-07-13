"""Queue #170 — poly game matchup title backfill (A2 title-backfill helper).

A Polymarket game is decomposed into sub-market rows (gotcha #18); the spread/prop
rows lose the "A vs. B" matchup, so the engine reads zero participants and can't
reproduce their event link. These test the pure recovery of the group matchup from
a sibling row's name (source-native, non-circular) and its idempotent stamping.
"""

from __future__ import annotations

from app.utils.polymarket_matchup_backfill import (
    group_matchup,
    matchup_from_name,
    needs_matchup_backfill,
)

_GROUP = [
    "Toronto Blue Jays vs. San Diego Padres",                 # moneyline
    "Toronto Blue Jays vs. San Diego Padres: O/U 11.5",       # total
    "Spread: San Diego Padres (-2.5)",                        # spread (one team)
    "1st 5 Innings Spread: Toronto Blue Jays (-1.5)",         # prop spread (one team)
    "Will the game go to extra innings?: Toronto Blue Jays vs. San Diego Padres",
]


def test_matchup_from_name_parses_matchup_rows_only():
    assert matchup_from_name("Toronto Blue Jays vs. San Diego Padres") == (
        "Toronto Blue Jays", "San Diego Padres")
    assert matchup_from_name("Toronto Blue Jays vs. San Diego Padres: O/U 11.5") == (
        "Toronto Blue Jays", "San Diego Padres")
    assert matchup_from_name("Spread: San Diego Padres (-2.5)") is None


def test_group_matchup_recovers_from_sibling():
    assert group_matchup(_GROUP) == "Toronto Blue Jays vs. San Diego Padres"


def test_group_matchup_none_for_non_game_group():
    assert group_matchup(["Will Trump win?", "Will Biden win?"]) is None
    assert group_matchup([]) is None


def test_needs_backfill_is_idempotent():
    # spread row with no matchup title → needs it
    assert needs_matchup_backfill("Spread: San Diego Padres (-2.5)", None) is True
    # already backfilled → no
    assert needs_matchup_backfill("Spread: San Diego Padres (-2.5)", "A vs. B") is False
    # a row whose own name already carries the matchup → no
    assert needs_matchup_backfill("Toronto Blue Jays vs. San Diego Padres", None) is False
