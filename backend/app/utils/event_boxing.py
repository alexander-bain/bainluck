"""Boxing adapter for the Event Concept framework — L2-86 (B5).

This module IS the "boxing as a config drop" deliverable: boxing is structurally
identical to UFC (see `event_ufc.py`) — Kalshi carries per-fight markets whose
tickers `KXBOXING-<YYMONDD><FIGHTERS>` (verified live 2026-07-12, e.g.
KXBOXING-26JUL04MASONBELL) each have two outcomes; fights sharing the DATE token
are one card; method/round/distance props ride the `KXBOXING<TYPE>-` prefixes.

So there is NO new page/engine code — this file is a `CombatSportConfig` plus the
named wrappers + adapter subclass that the hub / event-concept registry expect. The
one real difference from UFC is that boxing cards are NOT numbered ("UFC 329" has no
boxing analogue), so `number_re`/`fight_night_re` are omitted and a card is named by
its headline bout (`is_major` is always False).

Known v1 limitation: date-token grouping treats all same-day boxing fights as one
card. UFC runs one card per day so this is exact there; boxing sometimes runs
multiple same-day promotions, which would then co-list — acceptable for a "list
upcoming cards" v1 (mirrors the UFC model the queue endorsed).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.event_combat import (
    CombatEventAdapter,
    classify_prop,
    derive_concept,
    list_card_concepts,
    make_combat_config,
)

# Prop TYPE grammar — Kalshi boxing prop ticker prefixes (see utils/sport_keys.py).
_BOXING_PROP_TICKER_TYPES = {
    "KXBOXINGMOV": "method",       # Method of victory
    "KXBOXINGKNOCKOUT": "method",  # Knockout (a method of victory)
    "KXBOXINGROUNDS": "rounds",    # Total rounds
    "KXBOXINGVICROUND": "rounds",  # Victory in round
    "KXBOXINGDISTANCE": "distance",  # To go the distance
    "KXBOXING1MIN": "occurrence",  # 1-minute-fight novelty
}

# The whole boxing "adapter": constants over the shared combat engine. No numbering
# (boxing cards aren't numbered) → number_re / fight_night_re / strip_re omitted.
BOXING_CONFIG = make_combat_config(
    domain="boxing",
    llm_category="boxing",
    fight_prefix="KXBOXING",  # KXBOXING-<YYMONDD><FIGHTERS>; props are KXBOXING<TYPE>-…
    any_prefix="KXBOXING",    # any boxing ticker shares the card date-token
    prop_ticker_types=_BOXING_PROP_TICKER_TYPES,
)


# ---------------------------------------------------------------------------
# Named wrappers — parity with the UFC module's public surface (used by the hub
# prop-split classifier + upcoming lister and the event-concept registry).
# ---------------------------------------------------------------------------


def classify_boxing_prop(external_id: str | None, name: str | None) -> str | None:
    return classify_prop(BOXING_CONFIG, external_id, name)


def derive_boxing_concept(
    external_id: str | None, name: str | None, n_outcomes: int | None = None
) -> dict | None:
    return derive_concept(BOXING_CONFIG, external_id, name, n_outcomes)


async def list_boxing_card_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 20,
) -> list[dict]:
    return await list_card_concepts(BOXING_CONFIG, db, statuses=statuses, limit=limit)


class BoxingEventAdapter(CombatEventAdapter):
    def __init__(self):
        super().__init__(BOXING_CONFIG)
