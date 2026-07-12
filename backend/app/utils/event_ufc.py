"""UFC adapter for the Event Concept framework — slice 3, the co-equal variant
(#999, L2-72; completed in L2-84; refactored onto the shared combat engine in L2-86).

A UFC card has no single winner — it's a set of two-sided fights (+ props).
Verified live (2026-07-09..07-12): Kalshi carries per-fight markets with tickers
`KXUFCFIGHT-<DATE><FIGHTERS>` (e.g. KXUFCFIGHT-26JUL11MCGHOL), each with exactly 2
outcomes (fighter A / fighter B), category=mma. Fights sharing the DATE token are
one card. Model: the card's headline fight (latest commence_time) is `primary`
(rendered head-to-head via TwoSidedTimeline); every fight is a child (matchup rail).

L2-86 (B5) extracted the card-grouping / naming / prop-classification / envelope
logic into the domain-parameterized `event_combat` engine so boxing drops in as a
config (see `event_boxing.py`). This module is now a thin config: the UFC constants
+ named wrappers that keep the historical public API (`ufc_*`) stable for its
callers (search/typeahead in `routes/events.py`, the feed lister, the hub).
"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.event_combat import (
    CombatEventAdapter,
    any_card_token,
    card_label,
    card_number,
    card_token,
    classify_prop,
    combat_status,
    derive_concept,
    is_fight_market,
    list_card_concepts,
    make_combat_config,
)

# Numbered-card label, e.g. "UFC 329" out of "UFC 329: McGregor vs. Holloway 2".
_UFC_NUMBER_RE = re.compile(r"\bUFC\s*#?\s*(\d{2,4})\b", re.IGNORECASE)

# Leading "UFC 329: " / "UFC Fight Night: " / "Fight Night: " stripped from a subtitle.
_UFC_STRIP_RE = re.compile(
    r"^\s*(?:UFC\s*#?\s*\d{2,4}|UFC\s*Fight\s*Night|Fight\s*Night)\s*:?\s*",
    re.IGNORECASE,
)
_UFC_FIGHT_NIGHT_RE = re.compile(r"fight\s*night", re.IGNORECASE)

# Prop TYPE grammar. Kalshi ticker prefixes are the highest-precision signal.
_UFC_PROP_TICKER_TYPES = {
    "KXUFCMOV": "method",       # Method of Victory
    "KXUFCMOF": "method",       # Method of Finish
    "KXUFCROUNDS": "rounds",    # Round of Finish
    "KXUFCVICROUND": "rounds",  # Round of Victory
    "KXUFCDISTANCE": "distance",  # Go the Distance
    "KXUFCOCCUR": "occurrence",  # Will A and B fight at …?
}

# The whole UFC "adapter": constants over the shared combat engine.
UFC_CONFIG = make_combat_config(
    domain="ufc",
    llm_category="mma",
    fight_prefix="KXUFCFIGHT",  # KXUFCFIGHT-<YYMONDD><FIGHTERS>
    any_prefix="KXUFC",         # any UFC ticker shares the card date-token
    prop_ticker_types=_UFC_PROP_TICKER_TYPES,
    number_re=_UFC_NUMBER_RE,
    number_label="UFC",
    strip_re=_UFC_STRIP_RE,
    fight_night_re=_UFC_FIGHT_NIGHT_RE,
    fight_night_label="Fight Night",
)


# ---------------------------------------------------------------------------
# Named wrappers — the stable public API (kept for callers + the pure-helper
# unit tests). Each delegates to the shared engine with UFC_CONFIG.
# ---------------------------------------------------------------------------


def ufc_card_token(external_id: str | None) -> str | None:
    return card_token(UFC_CONFIG, external_id)


def ufc_any_card_token(external_id: str | None) -> str | None:
    return any_card_token(UFC_CONFIG, external_id)


def ufc_card_number(*texts: str | None) -> str | None:
    return card_number(UFC_CONFIG, *texts)


def ufc_card_label(main_event_name: str | None, extra_titles=()) -> tuple[str, bool]:
    return card_label(UFC_CONFIG, main_event_name, extra_titles)


def is_ufc_fight_market(external_id: str | None, n_outcomes: int) -> bool:
    return is_fight_market(UFC_CONFIG, external_id, n_outcomes)


def classify_ufc_prop(external_id: str | None, name: str | None) -> str | None:
    return classify_prop(UFC_CONFIG, external_id, name)


def ufc_status(latest_commence, now) -> str:
    return combat_status(latest_commence, now)


def derive_ufc_concept(
    external_id: str | None, name: str | None, n_outcomes: int | None = None
) -> dict | None:
    return derive_concept(UFC_CONFIG, external_id, name, n_outcomes)


async def list_ufc_card_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 20,
) -> list[dict]:
    return await list_card_concepts(UFC_CONFIG, db, statuses=statuses, limit=limit)


class UFCEventAdapter(CombatEventAdapter):
    def __init__(self):
        super().__init__(UFC_CONFIG)
