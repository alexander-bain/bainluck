"""#1529 — a segment of the match is its own shared class, never the match.

THE REVIEW FINDING (issue comment 6125893179). PR #10936 taught the game-markets
ROUTE a `segment_winner` label, but `scripts/capture_census.py` →
`capture_census.tally_market_rows` → `classify_game_market_class` never saw it:
the shared classifier still answered `other` for the named esports map and —
worse, in the opposite direction — `moneyline` for Kalshi's first-five-innings
book, which wears the game's own bare title:

    classify_game_market_class("Counter-Strike: 1WIN vs B8 - Map 1 Winner", hex, "esports")
        == "other"
    classify_game_market_class("Boston Red Sox at Baltimore Orioles",
                               "KXMLBF5-26SEP061335BOSBAL", "baseball_mlb")
        == "moneyline"      # identical to KXMLBGAME

`moneyline` is what settlement trusts: `venue_settlement_ends_the_match`
conjunct 1, `choose_settled_winner`, and the container's own-winner exclusion
all compare against it exactly. An F5 graded for a side passed all four
settlement conjuncts.

Guarded on the REAL consumers, both directions:
  * the classifier: segments -> `segment_winner`; whole-match, prop-container,
    player-prop and stage-winner controls unchanged;
  * the census: segments are their own row, counted in the denominator, out of
    `other` and out of `moneyline`;
  * settlement + container: an F5 / map winner can no longer end, settle or be
    excluded as the match; a KXMLBGAME winner still does.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils import capture_census as cc
from app.utils.container_game_winner import is_the_games_own_winner_market
from app.utils.event_completion import venue_settlement_ends_the_match
from app.utils.game_market_class import (
    classify_game_market_class,
    is_game_winner_market,
)
from app.utils.market_shape import SHAPE_DUEL
from app.utils.venue_settlement import choose_settled_winner

HEX = "0x5c0c5cd1a9b9c329fa03076140"
F5 = ("Boston Red Sox at Baltimore Orioles", "KXMLBF5-26SEP061335BOSBAL")
GAME = ("Boston Red Sox at Baltimore Orioles", "KXMLBGAME-26SEP061335BOSBAL")
MAP1 = ("Counter-Strike: 1WIN vs B8 - Map 1 Winner", HEX)
MATCH = ("Counter-Strike: 1WIN vs B8 - Match Winner", HEX)


# ── the classifier ──────────────────────────────────────────────────────────

SEGMENTS = [
    (*F5, "baseball_mlb"),
    ("Philadelphia vs Atlanta: First 5 Innings", "KXMLBF5-26SEP291400PHIATL", "baseball_mlb"),
    (*MAP1, "esports"),
    ("Phantom Academy vs. Noir Verse: Map 1", HEX, "esports"),
    ("Set 1 Winner: Aboian vs Martin", None, "tennis"),
    ("76ers vs. Celtics: 1H Moneyline", None, "basketball_nba"),
    ("Celtics at Knicks", "KXNBA1QWINNER-26MAY17BOSNYK", "basketball_nba"),
]


@pytest.mark.parametrize("name,external_id,sport", SEGMENTS)
def test_a_segment_is_a_segment_winner(name, external_id, sport):
    assert classify_game_market_class(name, external_id, sport) == "segment_winner"
    assert is_game_winner_market(name, external_id, sport) is False


UNCHANGED = [
    (*GAME, "baseball_mlb", "moneyline"),
    (*MATCH, "esports", "moneyline"),
    ("Yankees vs. Red Sox", HEX, "baseball_mlb", "moneyline"),
    ("2022 NBA Playoffs, Round 2: Who will win Celtics vs. Bucks?", None, None, "moneyline"),
    ("Game 3 Winner: Dodgers vs Padres", None, None, "moneyline"),
    # A "- Player Props" container stays `other` (decomposed elsewhere).
    ("Yankees vs. Red Sox - Player Props", HEX, "baseball_mlb", "other"),
    # A tournament-stage winner with no two sides is not a segment of a match.
    ("Brazil Presidential Election First Round Winner", None, None, "other"),
    ("Aaron Judge: Total Bases", "KXMLBTB-26SEP061335BOSBAL", "baseball_mlb", "player_prop"),
    ("Philadelphia vs Atlanta: First 5 Innings Total Runs", "KXMLBF5TOTAL-26SEP291400PHIATL", "baseball_mlb", "total"),
    # The first-inning run wears the game's title on KXMLBRFI; its name
    # vocabulary (NRFI) is already team_prop, and so is its ticker now.
    ("Washington Nationals vs. Detroit Tigers", "KXMLBRFI-26SEP091915WSHDET", "baseball_mlb", "team_prop"),
]


@pytest.mark.parametrize("name,external_id,sport,expected", UNCHANGED)
def test_whole_match_props_and_containers_keep_their_class(name, external_id, sport, expected):
    assert classify_game_market_class(name, external_id, sport) == expected


# ── the census ──────────────────────────────────────────────────────────────


def _row(sport, name, ext):
    # (sport, name, external_id, outcomes, well, vol_pos, vol_null, artifact)
    return (sport, name, ext, 2, 2, 2, 0, 0)


def test_the_census_counts_segments_as_their_own_row():
    rows = [
        _row("baseball_mlb", *GAME),
        _row("baseball_mlb", *F5),
        _row("esports", *MATCH),
        _row("esports", *MAP1),
        _row("esports", "Phantom Academy vs. Noir Verse: Map 1", HEX),
    ]
    by_sc, other_names = cc.tally_market_rows(rows)
    assert "segment_winner" in cc.CLASSES
    assert by_sc["baseball_mlb"]["moneyline"].markets == 1
    assert by_sc["baseball_mlb"]["segment_winner"].markets == 1
    assert by_sc["esports"]["moneyline"].markets == 1
    assert by_sc["esports"]["segment_winner"].markets == 2
    assert "other" not in by_sc["esports"]
    assert other_names == {}


def test_segments_stay_in_the_ceiling_denominator():
    """The ceiling is not paid by dropping segments: they count in the total."""
    games = {"baseball_mlb": 40}
    mlb = [_row("baseball_mlb", *GAME)] * 40 + [_row("baseball_mlb", *F5)] * 40
    # 9 unrecognized rows: 9 / 89 = 10.1% only because the 40 segment rows are
    # in the denominator; without them it would be 9 / 49 = 18%.
    mlb += [_row("baseball_mlb", f"Unrecognized question {i}", None) for i in range(9)]
    by_sc, _ = cc.tally_market_rows(mlb)
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    leak = [f for f in cc.capture_findings(games, by_sc, now=now) if f.kind == "classifier_leak"]
    assert len(leak) == 1 and "10%" in leak[0].detail and "of 89 markets" in leak[0].detail
    starved = [f for f in cc.capture_findings(games, by_sc, now=now) if f.kind == "starved_class"]
    assert starved == []  # 40 moneylines / 40 games: F5 rows are not needed to pay the floor


def test_an_f5_never_pays_the_moneyline_floor():
    games = {"baseball_mlb": 40}
    by_sc, _ = cc.tally_market_rows([_row("baseball_mlb", *F5)] * 40)
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    starved = [f for f in cc.capture_findings(games, by_sc, now=now) if f.kind == "starved_class"]
    assert len(starved) == 1


# ── settlement and the container ────────────────────────────────────────────


def test_a_settled_f5_cannot_end_the_match():
    cls = classify_game_market_class(*F5, "baseball_mlb")
    assert venue_settlement_ends_the_match(cls, "resolved", "api_settlement", True) is False


def test_a_settled_game_winner_still_ends_the_match():
    cls = classify_game_market_class(*GAME, "baseball_mlb")
    assert venue_settlement_ends_the_match(cls, "resolved", "api_settlement", True) is True


def test_a_graded_f5_or_map_is_not_the_match_verdict():
    home, away = "Baltimore Orioles", "Boston Red Sox"
    assert choose_settled_winner([(*F5, "Boston Red Sox")], home, away) is None
    assert choose_settled_winner([(*MAP1, "1WIN")], "1WIN", "B8") is None
    # Control: the whole-game book still names the winner.
    assert choose_settled_winner([(*GAME, "Boston Red Sox")], home, away) is not None


def test_an_f5_is_not_the_games_own_winner_market():
    assert is_the_games_own_winner_market(SHAPE_DUEL, *F5) is False
    assert is_the_games_own_winner_market(SHAPE_DUEL, *GAME) is True
