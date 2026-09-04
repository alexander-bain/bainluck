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

## Amendment, 2026-09-03 (D55, #2879): the ANCHOR KEY no longer counts digits

Everything above is the *comparison* of two raw `events.statpal_fixture_id`
values, and it still stands: that column is an untagged union, the only thing
distinguishing its two spaces is their length, and `compare_statpal_ids` has to
read the length to say `INCOMPARABLE` honestly.

The **anchor key** is a different question with a better answer available, and
it no longer uses that reading. `statpal_anchor_key` is qualified by the
**sport**, because the caller knows the sport for certain where the id's space
was only ever inferred. Counting digits gave three wrong answers at once the
moment a second sport arrived — NFL's 6-digit `contestid` filed into MLB's `s6`,
tennis's 7-digit id anchorable nowhere, NBA/NHL unmeasured — and none of them
raised. See `statpal_anchor_key` for the full argument and for the two-step
sequence that removes the legacy branch.

Read this way, the two functions disagree about nothing. One asks *"are these
two values from the same space?"*, which only the values can answer. The other
asks *"what is this fixture's identity?"*, which the caller can answer better
than the value can.

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


#: Anchor sources whose `source_id` is a COPY of a mutable column on `events`,
#: mapped to the column it was copied from. CERT-410 [P1].
#:
#: The distinction this table draws is the whole of that finding. For Kalshi and
#: Polymarket there is no id column on `events` at all, so the anchor row IS the
#: record — nothing exists that could drift out from under it. For these three
#: the anchor is a *cache of a column*, and the column is mutable and
#: non-unique: `repair_event_espn_id` re-keys `espn_id` and the source-intelligence
#: collision sweep clears it to NULL. A cache that outlives its source and keeps
#: its authority is not an identity; it is a stale assertion with the power to
#: absorb a different game.
#:
#: So the rule these three obey and the other two do not: **a scalar-derived
#: anchor is authoritative only while it still agrees with the column it was
#: copied from.** Read-side corroboration and re-key invalidation both key off
#: this map, so a fourth column-backed provider gets both behaviours by being
#: added here once.
SCALAR_DERIVED_ID_COLUMNS = {
    SOURCE_ESPN: "espn_id",
    SOURCE_ODDS_API: "external_id",
    SOURCE_STATPAL: "statpal_fixture_id",
}


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


def statpal_anchor_key(
    fixture_id: Optional[str], sport_key: Optional[str] = None
) -> Optional[AnchorKey]:
    """The anchor row for a StatPal fixture id, qualified by its SPORT (D55).

    ## Why the qualifier is the sport and not the id's shape (#2879, D55)

    The original version chose its namespace by counting digits — `^\\d{6}$` was
    `s6`, `^\\d{10}$` was `s10` — because the two id spaces we had measured
    differed in length and nothing else was available to tell them apart. That
    reading held exactly as long as one sport was in the table. It is wrong the
    moment a second arrives, and it is wrong in three different directions at
    once:

      * **NFL `contestid`s are 6 digits** (`280445`-`280772`, measured 374 of
        them on 2026-09-03). They would have been filed as `s6:` — MLB's space —
        and the unique key `(source, source_id, id_kind)` spans every sport.
      * **Tennis fixture ids are 7 digits** (`2629673`), matching neither
        regex, so tennis resolved to `None` and was *not anchorable at all*.
        Step 4 of the AUTHORITY program could have been built, tested, deployed
        and stamped nothing.
      * **NBA/NHL were simply unmeasured**, which is the same problem wearing a
        different hat: a rule that must be re-verified against every future id
        space is not a rule, it is a standing appointment.

    Alex ruled the same shape for Kalshi on 2026-08-21 — a `game` anchor is
    written only as `sport_key:game_id`, never bare — and `kalshi_anchor_key`
    below has done it since. D55 (2026-09-03) applies it here: the qualifier is
    the sport the fixture belongs to, which the caller knows for certain, rather
    than a property of the id that we are inferring. **The sport is data we are
    given; the namespace was a guess.**

    So a key is `sport_key:fixture_id`, and with `source='statpal'` on the row
    that is the `(provider, sport, id)` tuple D55 asks for.

    ## The legacy branch, and when it is deleted

    `sport_key=None` still returns the old digit-derived key. That is a
    deliberate, temporary bridge and it is the only reason this change can ship
    without darkening a live channel: the two production call sites are in
    `event_registry.py`, which is lane1's file under D50, so they cannot be
    updated in the same commit. The order is:

        1. this change      — accept a sport, keep the old answer without one
        2. lane1            — pass `sport_key=identity.sport_key` (two lines)
        3. this lane again  — re-key the 91 live `s6:` MLB anchors, then DELETE
                              the branch below and the digit path with it

    Until step 3 lands, `anchor_channel.anchor_key_for_claim` logs every
    unqualified StatPal request, so the bridge is *observable* rather than
    merely tolerated. Deleting it before step 2 would strand every StatPal
    anchor in the `NO_ANCHOR_CHANNEL` state that ruling 048's amendment exists
    to forbid, which is a worse answer than one deploy of a logged fallback.

    Refusing to write is still the correct failure for an id we cannot key:
    `None` here means *write nothing and match nothing*, and a `game` anchor on
    an unqualified id is the one outcome that can merge two real games.
    """
    if fixture_id is None:
        return None
    token = str(fixture_id).strip()
    if not token:
        return None

    # `None` means "this caller has not been updated yet" and takes the legacy
    # branch. A sport_key that is PRESENT but blank means the caller tried to
    # qualify and had nothing to qualify with, which is a different fact and
    # gets the conservative answer: refuse. Collapsing the two would let a
    # caller with an empty sport field fall silently back onto the digit rule —
    # the exact silence this ruling is removing.
    if sport_key is not None:
        qualifier = str(sport_key).strip()
        # A qualifier that is empty or carries the separator produces a key that
        # cannot be split back apart, and `anchor_is_current` re-derives the
        # sport from exactly that split. Refuse rather than emit a key its own
        # reader will misread.
        if not qualifier or ":" in qualifier:
            return None
        return AnchorKey(
            source=SOURCE_STATPAL,
            source_id=f"{qualifier}:{token}",
            id_kind=ANCHOR_KIND_GAME,
        )

    # --- LEGACY BRIDGE, deleted at step 3 above (D55 / #2879) ---
    ns = statpal_namespace(token)
    if ns is None:
        return None
    return AnchorKey(
        source=SOURCE_STATPAL,
        source_id=f"{ns}:{token}",
        id_kind=ANCHOR_KIND_GAME,
    )


#: The one sport whose StatPal id space is COARSER than our `sports.key`
#: vocabulary. See :func:`statpal_id_space`.
STATPAL_ID_SPACE_TENNIS = "tennis"

#: Prefix of every `sports.key` that is served by StatPal's single `tennis`
#: endpoint family (`tennis/daily/{token}`, `tennis/livescores`). Matched as a
#: prefix rather than enumerated because the tournament-suffixed keys are minted
#: per event (`tennis_atp_us_open`, `tennis_wta_wimbledon`, …) and an enumeration
#: would silently mis-space the next Slam we add.
_TENNIS_SPORT_KEY_PREFIX = "tennis"


def statpal_id_space(sport_key: Optional[str]) -> Optional[str]:
    """The StatPal ID SPACE a `sports.key` draws its fixture ids from.

    D55 says the anchor key is `(provider, sport, id)`, and `statpal_anchor_key`
    takes that middle term from the caller. The question this function answers is
    *which* sport name is the honest one to pass, and for every sport but one the
    answer is "ours" — `baseball_mlb`, `americanfootball_nfl` and StatPal's `mlb`
    and `nfl` are 1:1, so passing `sports.key` straight through names the space
    exactly (which is what `rekey_statpal_anchors_2879.py` does, and it stays
    correct).

    **Tennis is not 1:1, and passing `sports.key` there would break the property
    D55 exists to protect.** StatPal serves all of tennis from one endpoint family
    and numbers every match in one sequence: US Open match `2631673` and a
    Winston-Salem match are neighbours in the same run of integers. Our side
    splits the same matches across a growing set of keys — `tennis_atp`,
    `tennis_wta`, `tennis_other`, plus one per tournament (`tennis_atp_us_open`,
    `tennis_wta_wimbledon`, …), 30,115 rows over ~30 keys measured 2026-09-03.

    Qualifying by `sports.key` would therefore write `tennis_atp:2631673` and
    `tennis_atp_us_open:2631673` as two DIFFERENT keys for one StatPal match. The
    unique index `(source, source_id, id_kind)` would accept both, and the
    `COLLISION` that is this system's only *proof* that two of our rows are one
    game would never fire — on the sport where our duplicate rows are split
    across a generic and a tournament key, which is exactly the shape that makes
    them duplicates. Fragmenting one provider namespace into thirty is the same
    defect as collapsing thirty into one, arrived at from the other end.

    So: every `tennis*` key maps to `tennis`, and everything else is itself.
    `None` in, `None` out — a caller with no sport still has no sport, and
    `statpal_anchor_key` refuses an empty qualifier rather than inventing one.
    """
    if sport_key is None:
        return None
    token = str(sport_key).strip()
    if not token:
        return token
    if token.lower().startswith(_TENNIS_SPORT_KEY_PREFIX):
        return STATPAL_ID_SPACE_TENNIS
    return token


#: The two digit-derived prefixes this module used before D55, as they appear in
#: `event_provider_anchors.source_id`. Named here rather than rebuilt by the
#: re-key script, so that deleting the legacy branch above and finding this
#: constant's remaining readers is one grep instead of an archaeology exercise.
STATPAL_LEGACY_SOURCE_ID_PREFIXES = (
    f"{STATPAL_NS_SHORT}:",
    f"{STATPAL_NS_LONG}:",
)


def statpal_bare_fixture_id(source_id: Optional[str]) -> Optional[str]:
    """The unqualified fixture id inside a StatPal `source_id`, either shape.

    `baseball_mlb:354453` and `s6:354453` both yield `354453`. `None` for a
    value with no qualifier at all — which is not a shape this module has ever
    written, and is exactly the bare `source_id` the whole file exists to
    prevent.
    """
    if not source_id:
        return None
    token = str(source_id).strip()
    if ":" not in token:
        return None
    bare = token.split(":", 1)[1].strip()
    return bare or None


def statpal_legacy_source_id(key: Optional[AnchorKey]) -> Optional[str]:
    """The pre-D55 `source_id` the same fixture would have been written under.

    Returns `None` when there is no such value: a non-StatPal key, a key that is
    already legacy, or a fixture id whose digit count matched neither of the two
    shapes the old rule knew — which is the tennis case, and is precisely why the
    old rule had to go.

    This exists for the transition read in `anchor_channel.find_event_by_anchor`
    and for the re-key script, and it is deleted with them. It is written as a
    derivation rather than a stored mapping on purpose: a mapping would have to
    be maintained, and the whole point is that this has one job and then stops.
    """
    if key is None or key.source != SOURCE_STATPAL:
        return None
    if statpal_sport_from_source_id(key.source_id) is None:
        return None  # already legacy — nothing to translate back to
    bare = statpal_bare_fixture_id(key.source_id)
    ns = statpal_namespace(bare)
    if ns is None:
        return None
    return f"{ns}:{bare}"


def statpal_sport_from_source_id(source_id: Optional[str]) -> Optional[str]:
    """The sport qualifier of an already-written StatPal `source_id`, if it has one.

    `None` for a legacy `s6:`/`s10:` key and for anything unsplittable. Used by
    `anchor_channel.anchor_is_current`, which must re-derive a key from the bare
    column value and needs the SAME qualifier the writer used — reading it back
    off the stored key is exact and costs no lookup, where resolving the event's
    sport would cost a query to answer a question the key already answers.
    """
    if not source_id:
        return None
    token = str(source_id).strip()
    if ":" not in token:
        return None
    prefix = token.split(":", 1)[0]
    if f"{prefix}:" in STATPAL_LEGACY_SOURCE_ID_PREFIXES:
        return None
    return prefix or None


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
