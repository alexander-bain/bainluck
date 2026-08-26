"""The key function of #1946's anchor writer: a provider id -> an anchor triple.

`event_provider_anchors` exists (2026-08-24, #2119/#2114) and holds **0 rows**.
Filling it is #1946 Item 8, and Item 8's launch gate is a sink census that is
measurement-lane work under ruling 134. This module is the half of Item 8 that
the census does not gate: **deciding what an anchor row for a given provider id
would even be.** No DB, no clock, no I/O — the census governs which rows a
backfill may touch, not what a correct key looks like.

## What the table needs and why the shape is dangerous

The unique key is `(source, source_id, id_kind)` and `source_id` is a bare
`VARCHAR(200)`. Two properties follow, and both are load-bearing:

1. **Only `id_kind = 'game'` may anchor an absorption.** A Kalshi player-prop
   ticker and a Polymarket `conditionId` are `market`; a Polymarket event id is
   `container`. All are worth recording — they are how an anchor is discovered —
   but only one of them asserts *these two rows are the same game*.
2. **A `source_id` that is not namespace-qualified can collide across two
   different games.** That is not hypothetical. Alex already ruled on the Kalshi
   instance of it (2026-08-21, #1946 Item 7): a bare game-id token collides at
   0.0404%, the NCAA men's/women's specimen being the permanent argument, so a
   Kalshi anchor is written **only** as `sport_key:game_id` and **never bare**.

This module's whole job is to apply rule 2 to every provider rather than only to
the one where it was caught, because a collision in this table does not surface
as a bad row — it surfaces as **two different games absorbed into one**, which
ruling 048 exists to make impossible.

## The StatPal namespace, which is the currently-unhandled instance

`events.statpal_fixture_id` is an **untagged union of at least two id spaces**.
`app/services/statpal_api.py:489` builds it as
`str(item.get("id", item.get("fixture_id", "")))` — whatever the upstream JSON
happens to key it under, with no discriminator recorded. Queue 411 measured the
consequence on the 41 duplicate MLB groups since 2026-08-01: **0 groups share
any of the three provider ids**, and **21 hold *conflicting* StatPal ids** — one
6-digit (`354xxx`-`355xxx`), one 10-digit (`13291xxxxx`). One of each is the
duplicate pair on Alex's own home screen.

So on those 21 groups an equality join does not merely fail to fire. It reads as
**positive evidence the two rows are different games**, which is the worst of
the three possible answers. The fix is three-valued, not two-valued:

    AGREE        same namespace, same value   -> these are the same game
    CONFLICT     same namespace, different    -> these are different games
    INCOMPARABLE different namespaces         -> NO EVIDENCE EITHER WAY

`INCOMPARABLE` is the state the current code cannot express, and expressing it
is most of the value here. A comparison that cannot say "I don't know" will say
something else instead.

## What this module deliberately does NOT do

It does not absorb, does not write, does not read the database, and does not
loosen ruling 048 by a millimetre — `INCOMPARABLE` authorizes nothing. It only
ever *narrows* what may anchor: every unknown case returns `None` or
`id_kind='market'`, never `'game'`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# --- id_kind -------------------------------------------------------------------
# Only ANCHOR_KIND_GAME may anchor an absorption. The other two are recorded
# because they are how an anchor is DISCOVERED, never because they assert
# same-game.
ANCHOR_KIND_GAME = "game"
ANCHOR_KIND_MARKET = "market"
ANCHOR_KIND_CONTAINER = "container"

# --- sources (the `source` column, VARCHAR(32)) ---------------------------------
SOURCE_ODDS_API = "odds_api"
SOURCE_ESPN = "espn"
SOURCE_STATPAL = "statpal"
SOURCE_KALSHI = "kalshi"
SOURCE_POLYMARKET = "polymarket"

# Tennis is excluded from Kalshi `game` anchors by Alex's 2026-08-21 ruling: its
# tickers do not carry a per-game token that survives the sport_key qualifier.
_KALSHI_TENNIS_SPORT_KEYS = frozenset(
    {"tennis_atp", "tennis_wta", "tennis_itf", "tennis_itf_men", "tennis_itf_women"}
)

# --- StatPal namespaces ---------------------------------------------------------
# Named after their SHAPE, not after the endpoint we currently believe emits
# them, because the endpoint mapping is a production fact this module is not
# allowed to measure and the shape is right here in the value.
STATPAL_NS_SHORT = "s6"  # 6-digit, observed 354xxx-355xxx
STATPAL_NS_LONG = "s10"  # 10-digit, observed 13291xxxxx

_STATPAL_SHORT_RE = re.compile(r"^\d{6}$")
_STATPAL_LONG_RE = re.compile(r"^\d{10}$")

# The three-valued comparison verdicts.
AGREE = "AGREE"
CONFLICT = "CONFLICT"
INCOMPARABLE = "INCOMPARABLE"


@dataclass(frozen=True)
class AnchorKey:
    """One row's worth of `(source, source_id, id_kind)`, or a refusal.

    `frozen=True` on purpose: an anchor key that can be mutated after the
    `id_kind` check has been made is a key whose check means nothing.
    """

    source: str
    source_id: str
    id_kind: str

    @property
    def may_anchor_absorption(self) -> bool:
        """Only a `game` anchor asserts that two rows are the same game."""
        return self.id_kind == ANCHOR_KIND_GAME


def statpal_namespace(value: Optional[str]) -> Optional[str]:
    """Which StatPal id space `value` belongs to, or None if unrecognised.

    Unrecognised is a real and expected answer, not an error. A third namespace
    appearing upstream must land here as `None` — and therefore as
    `INCOMPARABLE` and as *not anchorable* — rather than being guessed into one
    of the two we know about.
    """
    if value is None:
        return None
    token = str(value).strip()
    if _STATPAL_SHORT_RE.match(token):
        return STATPAL_NS_SHORT
    if _STATPAL_LONG_RE.match(token):
        return STATPAL_NS_LONG
    return None


def compare_statpal_ids(a: Optional[str], b: Optional[str]) -> str:
    """Three-valued comparison of two `events.statpal_fixture_id` values.

    This is the function the 21 conflicting duplicate groups need. Today's
    two-valued `a = b` returns false for them, and every caller reads false as
    "different games". They are not different games; they are two rows written
    by two StatPal endpoints that number fixtures differently.

    A missing id on either side is `INCOMPARABLE`, never `CONFLICT` — absence of
    an id has never been evidence of anything, and reading `NULL != NULL` as
    disagreement is the exact mistake `_CENSUS_SQL` documents at its own
    `twin_count`.
    """
    ns_a, ns_b = statpal_namespace(a), statpal_namespace(b)
    if ns_a is None or ns_b is None:
        return INCOMPARABLE
    if ns_a != ns_b:
        return INCOMPARABLE
    return AGREE if str(a).strip() == str(b).strip() else CONFLICT


def statpal_anchor_key(fixture_id: Optional[str]) -> Optional[AnchorKey]:
    """The anchor row for a StatPal fixture id, namespace-qualified.

    Returns `None` — write nothing — when the namespace is unknown. That is the
    Kalshi bare-prefix ruling applied to the provider it was not written for:
    an unqualified `source_id` in a `(source, source_id, id_kind)` unique index
    is an invitation for two different games to collide on one key, and the
    consequence of that collision is an absorption, not a bad row.
    """
    ns = statpal_namespace(fixture_id)
    if ns is None:
        return None
    return AnchorKey(
        source=SOURCE_STATPAL,
        source_id=f"{ns}:{str(fixture_id).strip()}",
        id_kind=ANCHOR_KIND_GAME,
    )


def kalshi_anchor_key(ticker: Optional[str]) -> Optional[AnchorKey]:
    """The anchor row for a Kalshi ticker, under Alex's 2026-08-21 ruling.

    Verbatim constraints, implemented rather than paraphrased:

      * `game` anchors are written **only** as `sport_key:game_id`.
      * The **bare** `kalshi_game_id()` token must never anchor a `game`.
      * **Tennis** (`tennis_atp` / `tennis_wta` / `tennis_itf*`) stays
        `id_kind='market'`.

    Anything that fails those tests still yields a `market` anchor when a ticker
    exists at all: recording it is how the anchor is discovered later, and
    `market` asserts nothing about same-game.
    """
    if not ticker:
        return None
    from app.utils.prediction_market_matching import kalshi_game_id
    from app.utils.sport_keys import (
        get_sport_key_from_ticker,
        is_kalshi_game_level_ticker,
    )

    raw = str(ticker).strip()
    if not raw:
        return None

    # CERT-409 [P1]. `kalshi_game_id()` is a broad date-token extractor and
    # `get_sport_key_from_ticker()` resolves futures prefixes ON PURPOSE, so
    # neither is a game test. Inferring "game" from the pair promoted every
    # date-shaped futures ticker — a best-of-seven series (`KXMLBSERIES-...`)
    # carries both, and a series anchored as `game` can absorb one of its own
    # fixtures. The classification must be POSITIVE and asked directly.
    game_id = kalshi_game_id(raw)
    sport_key = get_sport_key_from_ticker(raw)

    if (
        is_kalshi_game_level_ticker(raw)
        and game_id
        and sport_key
        and sport_key not in _KALSHI_TENNIS_SPORT_KEYS
    ):
        return AnchorKey(
            source=SOURCE_KALSHI,
            source_id=f"{sport_key}:{game_id}",
            id_kind=ANCHOR_KIND_GAME,
        )
    # No game token, no sport qualifier, or tennis -> record it, but as a market.
    return AnchorKey(
        source=SOURCE_KALSHI, source_id=raw, id_kind=ANCHOR_KIND_MARKET
    )


def polymarket_anchor_key(
    *, condition_id: Optional[str] = None, event_id: Optional[str] = None
) -> Optional[AnchorKey]:
    """A Polymarket `conditionId` is a `market`; an event id is a `container`.

    Neither is ever a `game`. A Polymarket "event" groups sub-markets that may
    span several real fixtures (the `group_id` machinery in CLAUDE.md's
    prediction-market pipeline exists because of exactly that), so treating one
    as a game anchor would absorb across fixtures.
    """
    if condition_id and str(condition_id).strip():
        return AnchorKey(
            source=SOURCE_POLYMARKET,
            source_id=str(condition_id).strip(),
            id_kind=ANCHOR_KIND_MARKET,
        )
    if event_id and str(event_id).strip():
        return AnchorKey(
            source=SOURCE_POLYMARKET,
            source_id=str(event_id).strip(),
            id_kind=ANCHOR_KIND_CONTAINER,
        )
    return None


def espn_anchor_key(espn_id: Optional[str]) -> Optional[AnchorKey]:
    """ESPN game ids are global within ESPN, so they qualify as `game` bare.

    Recorded here rather than assumed: gotcha-adjacent measurement on #1204
    found `espn_id` COLLIDES across NCAA divisions *in our own table*, which is
    a linkage defect on our side rather than an ESPN namespace defect. The
    anchor is still `game`, because that is what the id means; the collision is
    the reconciliation rail's problem and it is visible there rather than being
    silently hidden by refusing to anchor.
    """
    if espn_id is None or not str(espn_id).strip():
        return None
    return AnchorKey(
        source=SOURCE_ESPN, source_id=str(espn_id).strip(), id_kind=ANCHOR_KIND_GAME
    )


def odds_api_anchor_key(external_id: Optional[str]) -> Optional[AnchorKey]:
    """The Odds API event id — global within that provider, so `game`."""
    if external_id is None or not str(external_id).strip():
        return None
    return AnchorKey(
        source=SOURCE_ODDS_API,
        source_id=str(external_id).strip(),
        id_kind=ANCHOR_KIND_GAME,
    )
