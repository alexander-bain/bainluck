"""Publish the venue's own names for upcoming fight cards (#4485).

A Discover fight card built from the schedule source alone is named after one of
its fights — "Alex Volkanovski vs Movsar Evloev" where a reader expects
"UFC 333". The name is in neither of our stores and is on ESPN's board, one
`name` per card. This producer reads that board and publishes it; the join and
the reasoning for it live in `app.utils.combat_card_names`.

WHY A PRODUCER AND NOT A SERVE-TIME READ. `GET /api/feed` never makes an
external call (CLAUDE.md, the Discover operating rules), and this is the reason
that rule exists: a card name is worth nothing to a reader who waited on ESPN
for it. The board changes on the order of weeks — a card gets its name when it
is announced and keeps it — so a slow cadence against a long TTL is the whole
design, and a missed pass costs nothing.

THE DARK READ IS NOT AN EMPTY BOARD. `get_combat_card_board` returns None when
ESPN did not answer, and this task publishes NOTHING on that reading rather than
overwriting a good listing with an empty one — gotcha #53, an empty 200 is a
response shape, not an absence. The previous listing stays until its TTL, which
is the behaviour worth having: yesterday's card names are still the right card
names.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.utils.combat_card_names import (
    ESPN_CARD_SPORT_KEYS,
    parse_espn_cards,
    store_card_names,
)

logger = logging.getLogger(__name__)

#: How far forward to ask for. The consumer is `list_card_concepts`, which lists
#: UPCOMING cards, and the far tail of that list is the Odds API's rumour
#: fixtures — cards ESPN does not list at all and which this can never name. A
#: season of real announcements is the useful span; asking for more buys rows
#: for nights no real card has been announced on yet.
FORWARD_DAYS = 150

#: A day back, so a card that is live or just finished still carries its name
#: while it is still on the feed.
BACKWARD_DAYS = 1


async def _refresh_espn_combat_cards() -> dict:
    """Read every combat board and publish one merged listing."""
    from app.services.espn_api import get_espn_service

    service = get_espn_service()
    now = datetime.now(timezone.utc)
    window = "%s-%s" % (
        (now - timedelta(days=BACKWARD_DAYS)).strftime("%Y%m%d"),
        (now + timedelta(days=FORWARD_DAYS)).strftime("%Y%m%d"),
    )

    cards: list[dict] = []
    dark: list[str] = []
    for sport_key in ESPN_CARD_SPORT_KEYS:
        board = await service.get_combat_card_board(sport_key, dates=window)
        if board is None:
            dark.append(sport_key)
            continue
        cards.extend(parse_espn_cards(board))

    # Every source dark, or a board that parsed to nothing: publish nothing. The
    # standing listing is strictly better than an empty one, and an empty one is
    # indistinguishable to the consumer from "the venue named no cards".
    if dark or not cards:
        logger.warning(
            "espn_combat_cards: not publishing (dark=%s, parsed=%d)", dark, len(cards)
        )
        return {"published": False, "cards": len(cards), "dark": dark}

    stored = store_card_names(cards)
    logger.info(
        "espn_combat_cards: %d cards over %s (stored=%s)", len(cards), window, stored
    )
    return {"published": stored, "cards": len(cards), "dark": dark}
