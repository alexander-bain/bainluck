"""live/039 — Polymarket writes the DRAW after the tournament, and it must parse.

Every name in here is a real production market name, measured 2026-09-02.

WHY THIS CLASS OF BUG IS WORTH A GUARD. `_CATEGORY_PREFIX_RE` is an allowlist,
and an allowlist that misses a spelling does not fail loudly — it hands the whole
string to `_extract_matchup_impl`, which returns None, which makes
`resolve_orientation` decline, which makes the Polymarket half of an event's
chart silently blank. Measured before the fix: 188 US Open main-draw match-winner
markets, every one unparseable, so no US Open event could ever draw a Polymarket
curve however good the linkage was.
"""

import re

import pytest

from app.utils.prediction_market_matching import (
    _strip_category_prefix,
    extract_matchup,
    extract_matchup_with_ticker_fallback,
    find_moneyline_outcome,
)


class _Outcome:
    """The two-outcome Yes/No shape a Polymarket binary market arrives in."""

    def __init__(self, name, probability, rank):
        self.name = name
        self.current_probability = probability
        self.rank = rank
        self.id = rank
        self.external_id = f"token-{rank}"


# Real names, real draws.
TOUR_LAST_MATCH_WINNERS = [
    ("US Open ATP: Ben Shelton vs Hubert Hurkacz", "Ben Shelton", "Hubert Hurkacz"),
    ("US Open ATP: Alexander Bublik vs Adrian Mannarino",
     "Alexander Bublik", "Adrian Mannarino"),
    ("US Open ATP: Rei Sakamoto vs Frances Tiafoe",
     "Rei Sakamoto", "Frances Tiafoe"),
    ("US Open WTA: Iva Jovic vs Magdalena Frech", "Iva Jovic", "Magdalena Frech"),
    ("US Open, Qualification ATP: Coleman Wong vs Alex Bolt",
     "Coleman Wong", "Alex Bolt"),
    ("US Open, Qualification WTA: Anca Todoni vs Yuliia Starodubtseva",
     "Anca Todoni", "Yuliia Starodubtseva"),
]


@pytest.mark.parametrize("name,team_a,team_b", TOUR_LAST_MATCH_WINNERS)
def test_tour_last_grand_slam_prefix_yields_the_matchup(name, team_a, team_b):
    """The whole point: these parse, and they parse to the right two players."""
    matchup = extract_matchup(name)
    assert matchup is not None, f"{name!r} still yields no matchup"
    assert matchup.team_a == team_a
    assert matchup.team_b == team_b


@pytest.mark.parametrize("name,_a,_b", TOUR_LAST_MATCH_WINNERS)
def test_tour_last_prefix_is_actually_stripped(name, _a, _b):
    """The mechanism, not just the outcome — so a future fix elsewhere that
    happens to make the parse work does not let the prefix rot back."""
    stripped = _strip_category_prefix(name)
    assert stripped != name
    assert ":" not in stripped, f"prefix only partly stripped: {stripped!r}"


def test_tour_first_spelling_still_parses():
    """The branch that already worked must keep working — the fix is additive."""
    matchup = extract_matchup("ATP US Open: Coleman Wong vs Alex Bolt")
    assert matchup is not None
    assert matchup.team_a == "Coleman Wong"


# ---------------------------------------------------------------------------
# The controls. Both must be green with AND without the fix.
# ---------------------------------------------------------------------------


AFC_WIMBLEDON = [
    "Wimbledon vs Newport",
    "Wimbledon vs Newport: First Half Spread",
    "Wimbledon vs Reading: BTTS",
]


@pytest.mark.parametrize("name", AFC_WIMBLEDON)
def test_afc_wimbledon_the_football_club_is_not_a_tennis_prefix(name):
    """`Wimbledon` is a literal in the prefix allowlist AND a London football
    club. The prefix must not eat the home team: these names carry no colon
    directly after `Wimbledon`, and the draw qualifier must not create one."""
    matchup = extract_matchup(name)
    assert matchup is not None
    assert matchup.team_a == "Wimbledon"
    assert matchup.team_b == "Newport" if "Newport" in name else True


PROP_MARKETS = [
    ("Set Handicap: Shelton (-1.5) vs Hurkacz (+1.5)", [("Yes", 0.525), ("No", 0.475)]),
    ("Set Handicap: Shelton (-2.5) vs Hurkacz (+2.5)", [("Yes", 0.275), ("No", 0.725)]),
    ("Set 1 Winner: Shelton vs Hurkacz", [("Yes", 0.610), ("No", 0.400)]),
    ("Set 2 Winner: Shelton vs Hurkacz", [("Yes", 0.615), ("No", 0.385)]),
    ("Game Spread: Shelton (-3.5) vs Hurkacz (+3.5)", [("Yes", 0.5), ("No", 0.5)]),
    ("Shelton vs. Hurkacz: Match O/U 36.5", [("Over", 0.595), ("Under", 0.405)]),
    ("Ben Shelton vs. Hubert Hurkacz: Total Sets O/U 3.5",
     [("Over", 0.65), ("Under", 0.355)]),
]


@pytest.mark.parametrize("name,outcomes", PROP_MARKETS)
def test_props_still_refuse_to_orient(name, outcomes):
    """🔴 THE SAFETY PROPERTY, and it is the one that matters most.

    A Polymarket prop has the SAME two-outcome Yes/No shape as the match winner,
    and `is_game_winner_market` gates Kalshi only — it returns False for every
    Polymarket row, so `select_primary_market` falls through to "lowest market
    id", which is "oldest row" and is a coin flip between the match winner and a
    Set Handicap. Nothing downstream would notice: a Set Handicap curve on the
    favourite ends on the right side, so even
    `contradicts_known_winner` passes it. The only thing standing between a
    reader and a confidently-wrong win-prob chart is that these names do not
    parse into a matchup — so if this test ever goes red, the prefix has been
    widened too far and the drain must be stopped before it runs.
    """
    ordered = [_Outcome(n, p, i + 1) for i, (n, p) in enumerate(outcomes)]
    matchup = extract_matchup_with_ticker_fallback(name, external_id=None)
    resolved = (
        find_moneyline_outcome(ordered, matchup, "Shelton", "Hurkacz")
        if matchup
        else None
    )
    assert resolved is None, f"{name!r} oriented as a match winner: {resolved}"


@pytest.mark.parametrize("name,team_a,team_b", TOUR_LAST_MATCH_WINNERS[:4])
def test_match_winner_orients_end_to_end(name, team_a, team_b):
    """The mirror of the safety property: the real match winner DOES orient,
    through the same chain the live poll and the WS fast lane use."""
    home = team_a.split()[-1]
    away = team_b.split()[-1]
    ordered = [_Outcome("Yes", 0.68, 1), _Outcome("No", 0.32, 2)]
    matchup = extract_matchup_with_ticker_fallback(name, external_id=None)
    assert matchup is not None
    resolved = find_moneyline_outcome(ordered, matchup, home, away)
    assert resolved is not None, f"{name!r} did not orient"
    outcome, yes_is_home = resolved
    assert outcome.name == "Yes"
    assert yes_is_home is True


def test_prefix_regex_does_not_swallow_an_unbounded_qualifier():
    """The qualifier is a closed set, not `[^:]*`. An open-ended one would strip
    the first half of any `<Tournament> <anything>:` name and take a team with
    it."""
    from app.utils.prediction_market_matching import _CATEGORY_PREFIX_RE

    # A tournament followed by something that is NOT a draw qualifier must not
    # match — the name keeps its prefix and falls through to the other variants.
    assert not re.match(
        _CATEGORY_PREFIX_RE, "US Open Kowalczyk: Player A vs Player B"
    )
