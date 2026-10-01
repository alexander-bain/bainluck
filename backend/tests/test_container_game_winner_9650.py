"""A game's own winner market is the game card, never a related question. #9650.

Every row here is a REAL production `futures_markets` row, read through
`POST /api/admin/db-query` on 2026-09-30 (~23:30Z): id, source, name,
external_id and `market_type` exactly as stored. PHI@ATL NLWC Game 1 is event
15320289; Steelers at Browns (NFL 2026 Week 4) is event 14780550, whose three
"who wins" cards the published hub `nfl-2026-week-4` served that evening.

Each half of the rule is load-bearing, and the controls are the rows that prove
it: the Polymarket event wrapper (class says moneyline, shape says `field`) and
the spread duels (shape says `duel`, class says spread).
"""

from __future__ import annotations

import pytest

from app.utils.container_game_winner import is_the_games_own_winner_market

#: (id, source, name, external_id, market_type) — the game's own winner markets.
WINNERS = [
    (62924885, "kalshi", "Game 1: Philadelphia vs Atlanta", "KXMLBGAME-26SEP291400PHIATL", "duel"),
    (63026432, "polymarket", "Philadelphia Phillies vs. Atlanta Braves",
     "0x4b89caf655c9602405a1c0366a1de9cc976f88d3b85ff69a808754ed2e81f36b", "duel"),
    (62924880, "kalshi", "Game 2: Chicago WS vs Houston", "KXMLBGAME-26SEP301700CWSHOU", "duel"),
    (61894632, "kalshi", "PIT Steelers vs CLE Browns", "KXNFLGAME-26OCT01PITCLE", "duel"),
    (62784863, "polymarket", "Steelers vs. Browns", "0x8a9f8be5bef9bc8d36c7895707a4f256", "duel"),
]

#: Questions on the same games that are NOT the game's winner and must stay.
QUESTIONS = [
    # Class says moneyline (bare matchup title); shape says field — Polymarket's
    # event wrapper, 27 / 217 outcomes led by totals. Not the game's winner.
    (63026431, "polymarket", "Philadelphia Phillies vs. Atlanta Braves", "1097824", "field"),
    (59369584, "polymarket", "Steelers vs. Browns", "885112", "field"),
    # Shape says duel; class says spread.
    (63026433, "polymarket", "Spread: Atlanta Braves (-1.5)",
     "0x5c0c5cd1a9b9c329fa03076140", "duel"),
    (63031613, "polymarket", "1st 5 Innings Spread: Atlanta Braves (-1.5)",
     "0xd74e5beba56e85634d3dd3a530", "duel"),
    # A segment's winner is not the game's.
    (None, "polymarket", "Steelers vs. Browns: 1H Moneyline", "0xaf5b520fb30ba7a72e51019b197b", "duel"),
    (63153623, "kalshi", "Philadelphia vs Atlanta: 9th Inning Winner", "KXMLBINNINGWIN-26SEP291400PH", "field"),
    (62972601, "kalshi", "Philadelphia vs Atlanta: First 5 Innings", "KXMLBF5-26SEP291400PHIATL", "field"),
    (62932006, "kalshi", "Philadelphia vs Atlanta: Total Runs", "KXMLBTOTAL-26SEP291400PHIATL", "quantity"),
    (None, "kalshi", "Chicago C vs San Diego: Outs Recorded", "KXMLBOUTS-26SEP292200CHCSD", "duel"),
]


@pytest.mark.parametrize("row", WINNERS, ids=lambda r: str(r[0]))
def test_the_games_winner_market_is_recognised(row):
    _, _, name, external_id, market_type = row
    assert is_the_games_own_winner_market(market_type, name, external_id) is True


@pytest.mark.parametrize("row", QUESTIONS, ids=lambda r: r[2])
def test_every_other_question_on_the_game_stays(row):
    _, _, name, external_id, market_type = row
    assert is_the_games_own_winner_market(market_type, name, external_id) is False


@pytest.mark.parametrize("row", WINNERS, ids=lambda r: str(r[0]))
def test_an_unshaped_winner_is_kept_not_guessed(row):
    # NULL shape (never classified) or any non-duel shape keeps the market: a
    # duplicate we failed to recognise is visible, a dropped question is not.
    _, _, name, external_id, _ = row
    assert is_the_games_own_winner_market(None, name, external_id) is False
    assert is_the_games_own_winner_market("binary", name, external_id) is False
