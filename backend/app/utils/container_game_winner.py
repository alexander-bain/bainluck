"""A game's own winner market is the game card, never a related question. #9650 (v3).

**SHIP: a reader opening an NFL week or the MLB postseason sees each game once,
with one number for who wins it — not the game card plus a Kalshi card and a
Polymarket card asking the same question underneath.** (Pillar: MATCHING /
DISCOVER.)

The game card a collection serves is `GET /api/events`' card, and its number is
the blend: the venues' game-winner markets are already inside it. Admitting
those markets as members as well put the same question on the hub two or three
times (the published NFL 2026 Week 4 served Steelers at Browns with the game
card plus 61894632 Kalshi and 62784863 Polymarket under "Related questions").
The blend is the product: one number per question.

THE TEST IS SHAPE AND CLASS, BOTH STORED OR SHARED, NEVER A NEW NAME RULE.
`futures_markets.market_type` must be `duel` (two named sides, `market_shape`),
and the shared per-game classifier (`game_market_class`) must call it the
moneyline. Each half alone is wrong on real rows:

* class alone admits Polymarket's event wrapper — "Steelers vs. Browns", shape
  `field`, 217 outcomes led by "O/U 18.5" — because its title is a bare matchup;
* shape alone admits every spread duel ("Spread: Atlanta Braves (-1.5)"), 930 of
  the 1,000 NFL/MLB duels read on 2026-09-30.

A NULL or other shape keeps the market (a duplicate we failed to recognise is
visible; a question we wrongly dropped is not). Segment winners ("1H
Moneyline", "1st Quarter Winner", "First 5 Innings") are not the game and stay.

An excluded market is accounted for in the adapter's ``excluded`` report under
`EXCLUDED_GAME_WINNER_MARKET`; it is not a gap and never makes a pass partial.
"""

from __future__ import annotations

from typing import Optional

from app.utils.game_market_class import classify_game_market_class
from app.utils.market_shape import SHAPE_DUEL

#: The ``excluded`` key both adapters report a game's own winner market under.
EXCLUDED_GAME_WINNER_MARKET = "game_winner_is_the_game_card"


def is_the_games_own_winner_market(
    market_type: Optional[str], name: Optional[str], external_id: Optional[str]
) -> bool:
    """True when this market, linked to a member game, decides that game."""
    if market_type != SHAPE_DUEL:
        return False
    return classify_game_market_class(name or "", external_id) == "moneyline"
