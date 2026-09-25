"""
Polymarket prediction market polling task.

Fetches sports and non-sports prediction market data from Polymarket's
public API (no API key required). Stores as futures markets/outcomes
with source="polymarket".
"""

import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text

from app.tasks.base import get_task_session
from app.utils.feed_market_quality import (
    FEED_PHANTOM_MIN_SPREAD,
    is_empty_book_midpoint,
    is_fabricated_midpoint,
)
from app.utils.kalshi_empty_book import book_refutes_price  # #7548
from app.utils.winner_field_coherence import (
    DUPLICATE_CONDITION_LEG_SQL,
    count_near_certain,
    field_is_incoherent,
)
from app.utils.content_understanding import (  # CU-1 clause (2), #5273
    CONTENT_UNDERSTANDING_KEY,
    build_content_understanding,
)
from app.utils.price_change_stamp import price_changed_at_value  # #2024
from app.utils.settled_price import (  # #5246 / #7767
    SETTLED_NO_PRICE,
    SETTLED_YES_PRICE,
    settled_price_set_sql,
    settlement_pending_sql,
)
from app.utils.futures_rank import rerank_market_field_stmt  # #6598
from app.utils.futures_liveness import preserve_venue_settled  # #2222
from app.utils.venue_competition import POLYMARKET_EVENT_SLUG_KEY  # #8636
from app.utils.event_taxonomy import NON_SPORT_CATEGORIES  # #7814 — see below
from app.utils.event_completion import (  # #6073
    POLYMARKET_VENUE_COMMENCE_SOURCE,
)
from app.utils.name_normalization import (  # #6073 CERT-2847
    strip_diacritics,
)
from app.utils.prediction_market_matching import (  # #6073 CERT-2840
    extract_matchup_with_ticker_fallback,
)
from app.utils.pair_opening_coherence import (
    OK as PAIR_OPENING_OK,
    classify_pair_opening,
    classify_pair_price,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Untradeable-book guard (#1578, the durable half of #1574)
# =========================================================================

# UX-P011 stopped Discover from SHOWING a price manufactured by averaging a
# spread nobody will trade inside. This stops the poller from WRITING one, so the
# number never exists on any surface.
#
# Two predicates, because the write path has two distinct situations:
#
#   is_fabricated_midpoint(prob, bid, ask)   — imported from the read side. For a
#       price handed to us (Gamma's opaque `outcome_prices`): decline it only when
#       it IS the midpoint of a wide book. If it is something else, it came from
#       somewhere else and the #151 evidence gate judges it.
#   is_empty_book_midpoint(prob, bid, ask)   — also imported from the read side
#       (#5247), and paired with the one above because the two have complementary
#       blind spots on ONE payload shape. See the #6676 comment at the call site.
#   _poly_book_is_untradeable(bid, ask)      — for a midpoint WE compute ourselves
#       (the bid/ask fallback, the websocket stream). No opacity, so the width
#       test alone settles it.
#
# The threshold is deliberately the SAME constant the read side uses, imported
# rather than restated, so "untradeable" has exactly one meaning in this codebase.
# It is measured, not tuned (see FEED_PHANTOM_MIN_SPREAD): across the 2026-08-07
# production feed the spread distribution is bimodal with an empty middle, and any
# value in [0.16, 0.43] is equivalent. Do not turn it into a knob.
#
# Why this is not redundant with the `has_market` evidence gate below: that gate
# (Queue #151) asks whether a book EXISTS — `best_bid > 0` is satisfied by a 2c
# bid on a 2c/94c book. It never asks whether the book is TRADEABLE. Measured on
# production 2026-08-07, resolved+graded Polymarket outcomes carrying a book:
#
#   cohort                  n        mean stored price   actual win rate
#   everything else         47,207   0.3444              0.3264   <- calibrated
#   wide-spread midpoint     1,580   0.5003              0.0013   <- fabrication
#
# The phantom cohort asserts 50% and wins twice in 1,580. #151 fixed half of this
# and its own comment predicted the rest; this is the other half.
#
# Note this guard can only ever DECLINE to write. Every caller is
# `if prob is None or prob <= 0: continue`, so returning None skips the upsert
# entirely — it never nulls an existing stored price (gotcha #21, forward-only).


def _poly_book_is_untradeable(
    best_bid: Optional[float],
    best_ask: Optional[float],
) -> bool:
    """True if this Polymarket order book is too wide for its midpoint to be a price.

    Mirrors ``is_fabricated_midpoint`` in ``app/utils/feed_market_quality.py``:

    - A missing side is the WIDEST possible quote on that side (no bid = 0.0, no
      ask = 1.0), because "nobody will buy this at any price" is a wide book, not a
      missing one.
    - Both sides absent means there is no order book at all. The rule does not
      apply, so model-priced and derived rows pass through untouched — by
      construction, not by exemption.
    """
    if best_bid is None and best_ask is None:
        return False
    bid = 0.0 if best_bid is None else float(best_bid)
    ask = 1.0 if best_ask is None else float(best_ask)
    return (ask - bid) >= FEED_PHANTOM_MIN_SPREAD


# =========================================================================
# Tag-to-category mapping
# =========================================================================

# Map Polymarket tags to our internal llm_sport_category values.
# Polymarket provides rich tagging — use it to avoid unnecessary LLM calls.
_TAG_TO_CATEGORY: dict[str, str] = {
    # Sports
    "nba": "basketball",
    "basketball": "basketball",
    "ncaab": "basketball",
    "wnba": "basketball",
    "nfl": "football",
    "football": "football",
    "ncaaf": "football",
    "college football": "football",
    "mlb": "baseball",
    "baseball": "baseball",
    "nhl": "hockey",
    "hockey": "hockey",
    "ufc": "mma",
    "mma": "mma",
    "fighting": "mma",
    "soccer": "soccer",
    "epl": "soccer",
    "premier league": "soccer",
    "la liga": "soccer",
    "champions league": "soccer",
    "ucl": "soccer",
    "bundesliga": "soccer",
    "serie a": "soccer",
    "mls": "soccer",
    "ligue 1": "soccer",
    "liga mx": "soccer",
    "copa america": "soccer",
    "world cup": "soccer",
    "fifa": "soccer",
    "golf": "golf",
    "pga": "golf",
    "masters": "golf",
    "tennis": "tennis",
    "atp": "tennis",
    "wta": "tennis",
    "wimbledon": "tennis",
    "us open tennis": "tennis",
    # Q493: Polymarket tags Setka/TT-Cup events "Table Tennis" (+ "Setka") and
    # real ATP/WTA events "Tennis". Both were true all along and neither was
    # read: "table tennis" was absent here, so a Setka event fell through to the
    # "sports" catch-all and could only be rescued by the #1230 child-prop
    # heuristic. Honouring the source's own tag is strictly stronger than
    # inferring the sport from a games threshold.
    "table tennis": "table_tennis",
    "table-tennis": "table_tennis",
    "setka": "table_tennis",
    # #6651 (Alex's 2026-09-16 phone test, #6444): "Attractive 2027 PPA Tour
    # finals for women card never explains its sport/league." The card could
    # not, because the row has nothing to say — `llm_sport_category`, `sport`
    # and `sport_name` are all NULL, and `discover/FuturesCard.tsx:130` falls
    # back through all three to the literal string "Markets".
    #
    # The venue knew all along. Read off Gamma 2026-09-17, all three live PPA
    # events carry the sport as their own tag:
    #
    #     1024935  2027-ppa-tour-finals-to-reach-semifinals-mens
    #     1024933  2027-ppa-tour-finals-player-to-qualify-mens
    #     1024934  2027-ppa-tour-finals-player-to-qualify-womens
    #         all three: labels ['PPA', 'Sports', 'Pickleball']
    #
    # `pickleball` was not here, so the specific-tag loop missed, the `sports`
    # arm returned (championship, None), and arm 2's `categorize_by_rules` /
    # `detect_league` found nothing in "2027 PPA Tour Finals…" — measured
    # ('championship', None, 'fallback') on all four production titles. Unlike
    # the AFL case below the fallback does not GUESS wrong here; it declines,
    # which is why the row is NULL rather than mislabelled.
    #
    # Measured population 2026-09-17, and the split is by status, not by row:
    # 178 OPEN polymarket rows NULL, against 141 resolved already carrying
    # `pickleball` and 18 `tennis`. So this is not a new value — it is the one
    # this family already settles on once anything classifies it, and the live
    # cohort is exactly the half a reader meets.
    #
    # `ppa` is deliberately NOT mapped: it is the tour, not the sport, and the
    # sport tag is present on every event. One key, matched by the venue's own
    # word for the sport.
    "pickleball": "pickleball",
    "boxing": "boxing",
    "cricket": "cricket",
    "ipl": "cricket",
    "rugby": "rugby",
    # #6411 (#6377's follow-up). Polymarket tags every Aussie Rules event with the code
    # it is actually played under — `afl` or `aflw`, read off Gamma 2026-09-15
    # (`afl-haw-bri-2026-09-19` tags `[sports, games, afl]`; `aflw-haw-nmk-
    # 2026-09-18` tags `[sports, games, aflw]`) — and NEITHER was read here, so
    # `_tags_to_category` fell through to the `sports` catch-all and the sport
    # was then GUESSED from the club nicknames. Hawks, Suns, Kangaroos read as
    # basketball; measured over 30 days, 17 fixtures scattered across THREE
    # unrelated catch-alls (`basketball_other` 11, `americanfootball_other` 4,
    # `motorsport_other` 3) — the Q453 unmapped-series signature.
    #
    # #6377 stopped the MINT (both keys are in `ODDS_API_COVERED_PREFIXES`, so
    # `covered_league_for_matchup` refuses). It could not make the market LINK,
    # because the guess survives in the stored category. Measured 2026-09-15,
    # and this is the user-visible half — 3 of 3 upcoming AFL/AFLW fixtures:
    #
    #     15312400 aussierules_aflw  Hawthorn v North Melbourne   0 markets
    #     15312509 basketball_other  Hawthorn v North Melbourne   1 market
    #     15310885 aussierules_afl   Hawthorn v Brisbane          0 markets
    #     15311099 basketball_other  Hawthorn v Brisbane          1 market
    #     15312406 aussierules_aflw  Essendon v Gold Coast        0 markets
    #     15312508 basketball_other  Essendon v Gold Coast        1 market
    #
    # The real game shows no Polymarket price; its phantom twin holds it. That
    # is #5544's defect one competition over, against the marquee axiom.
    #
    # Honouring the tag is what links it: the rows that already reach
    # `llm_sport_category='aussierules'` — by the title fallback, which gets it
    # right only some of the time — DO land on the real fixture (market 59487691
    # -> 15290839 `aussierules_afl`; 60359740 -> 15306868 `aussierules_aflw`).
    # The tag makes that outcome deterministic instead of a coin toss.
    #
    # Both codes map to the one category because `aussierules` is the sport; the
    # COMPETITION is resolved downstream off `teams`, where all 48 clubs are
    # present (30 `aussierules_afl` + 18 `aussierules_aflw`, read 2026-09-15).
    # Distinguishing the two here would put a competition in a sport-category
    # field, and `LLM_CATEGORY_TO_SPORT_PREFIX` has no key to receive it.
    # CERT-2924's required repair, `6411-READ-AFL-WOMEN-VENUE-LABEL`. THE KEYS
    # HERE ARE MATCHED AGAINST TAG **LABELS**, NOT SLUGS: `_parse_event` stores
    # `tag.get("label", "")` (polymarket_api.py), so the slug never reaches this
    # map. Read off Gamma 2026-09-15, the two codes do NOT agree —
    #
    #     afl-haw-bri-2026-09-19   label 'AFL'         slug 'afl'
    #     aflw-haw-nmk-2026-09-18  label 'AFL Women'   slug 'aflw'
    #
    # — so `aflw` alone matched nothing and the women's code, which is 8 of the
    # 10 fixtures the venue currently lists and 2 of this ship's 3 named
    # specimens, kept falling through to the basketball guess. The map's own
    # convention already anticipated this: every hyphenated slug it carries has
    # its spoken label beside it (`table tennis` / `table-tennis`, `horse
    # racing` / `horse-racing`). `aflw` was a slug with no label twin.
    #
    # The slug forms are kept because `_parse_event` also accepts a raw list of
    # strings, and nothing guarantees which shape an endpoint sends.
    "afl": "aussierules",
    "afl women": "aussierules",
    "aflw": "aussierules",
    "motorsports": "motorsports",
    "f1": "motorsports",
    "formula 1": "motorsports",
    "nascar": "motorsports",
    "indycar": "motorsports",
    "motogp": "motorsports",
    "olympics": "olympics",
    "olympic": "olympics",
    "summer olympics": "olympics",
    "winter olympics": "olympics",
    "esports": "esports",
    "gaming": "esports",
    "horse racing": "horse_racing",
    "horse-racing": "horse_racing",
    "kentucky derby": "horse_racing",
    "lacrosse": "lacrosse",
    # #8507: the venue tags every chess event `Chess` and this key was absent,
    # so the loop skipped it and returned on the next tag it knew. Read off
    # Gamma 2026-09-25:
    #
    #     775267   46th FIDE Chess Olympiad Open Tournament Winner
    #                  ['Chess', 'Sports', 'Esports']           -> was esports
    #     1064637  Titled Tuesday Winner: September 29
    #                  ['Sports', 'Chess', 'Titled Tuesday', 'Recurring'] -> was None
    #
    # so the Olympiad sat on /hub/esports and the Titled Tuesday cards named no
    # sport. `chess` is the value the resolved history already settles on (160
    # `championship` + 401 `game_prop` rows), and it has no key in
    # `LLM_CATEGORY_TO_SPORT_PREFIX`, so it labels the card and opens no rail.
    "chess": "chess",
    "cycling": "other",
    "swimming": "olympics",
    "track and field": "olympics",
    "athletics": "olympics",
    # Non-sports
    "politics": "politics",
    "elections": "politics",
    "trump": "politics",
    "congress": "politics",
    "senate": "politics",
    "entertainment": "entertainment",
    "oscars": "entertainment",
    "movies": "entertainment",
    "music": "entertainment",
    "tv": "entertainment",
    "awards": "entertainment",
    "grammys": "entertainment",
    "emmys": "entertainment",
    "crypto": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "solana": "crypto",
    "defi": "crypto",
    "nft": "crypto",
    "economy": "economics",
    "fed": "economics",
    "inflation": "economics",
    "gdp": "economics",
    "interest rates": "economics",
    "stocks": "economics",
    "stock market": "economics",
    "tech": "tech",
    "ai": "tech",
    "science": "tech",
    "spacex": "tech",
    "apple": "tech",
    "google": "tech",
    "weather": "weather",
    "climate": "weather",
    "hurricane": "weather",
    "temperature": "weather",
    # Geopolitics / International
    "geopolitics": "geopolitics",
    "war": "geopolitics",
    "ukraine": "geopolitics",
    "russia": "geopolitics",
    "china": "geopolitics",
    "nato": "geopolitics",
    "middle east": "geopolitics",
    "israel": "geopolitics",
    "iran": "geopolitics",
    "north korea": "geopolitics",
    "nuclear": "geopolitics",
    "sanctions": "geopolitics",
    "diplomacy": "geopolitics",
    "conflict": "geopolitics",
    # Legal / Regulatory
    "legal": "legal",
    "supreme court": "legal",
    "scotus": "legal",
    "regulation": "legal",
    "lawsuit": "legal",
    "trial": "legal",
    "indictment": "legal",
    # Health / Science
    "health": "health",
    "pandemic": "health",
    "covid": "health",
    "vaccine": "health",
    "fda": "health",
    "bird flu": "health",
    "virus": "health",
    # Space / Science
    "space": "tech",
    "nasa": "tech",
    "mars": "tech",
    "rocket": "tech",
    # Finance (more specific)
    "finance": "economics",
    "markets": "economics",
    "wall street": "economics",
    "ipo": "economics",
    "earnings": "economics",
    "bonds": "economics",
    "commodities": "economics",
    "real estate": "economics",
    "housing": "economics",
    "tariffs": "economics",
    "trade war": "economics",
    # Education / Academic
    "education": "culture",
    "university": "culture",
    "nobel": "culture",
    # Social / Culture
    "social media": "culture",
    "tiktok": "culture",
    "twitter": "culture",
    "celebrity": "entertainment",
    "pop culture": "entertainment",
    # Broad catch-alls
    "culture": "entertainment",
    "world": "politics",
    "news": "politics",
    "global": "geopolitics",
    "environment": "weather",
    # Note: "sports" is NOT in this dict — it's handled specially in
    # _tags_to_category() as a fallback that returns ("championship", None)
}

# Categories that map to "championship" internal category for sport-linked futures
_SPORT_CATEGORIES = {
    "basketball", "football", "baseball", "hockey", "mma", "soccer",
    "golf", "tennis", "boxing", "cricket", "rugby", "motorsports",
    "olympics", "esports", "horse_racing", "lacrosse",
    # #6411 (#6377's follow-up), and the same reason `table_tennis` is below: without it
    # the `afl`/`aflw` entries above would return ("aussierules", "aussierules")
    # rather than ("championship", "aussierules"), putting a SPORT name in the
    # internal category field. `championship` is what these rows already carry
    # when the title fallback classifies them (production 2026-09-15: 20
    # `aussierules` markets on `championship`, 3 on `game_prop`), so honouring
    # the tag must be byte-identical to the fallback's answer, not a new shape.
    "aussierules",
    # Q493: present so a "Table Tennis" tag yields ("championship",
    # "table_tennis") — byte-identical to what arm 1 has always returned. This
    # set is read ONLY by _tags_to_category above; the link-rate denominator is
    # a separate list (`_LINK_RATE_SPORT_CATEGORIES`, admin_matching.py) and
    # table_tennis is deliberately absent from it, as #1230 requires.
    "table_tennis",
    # #6651, and present for exactly the reason `table_tennis` above is: without
    # it the `pickleball` tag entry would return ("pickleball", "pickleball")
    # and put a SPORT name in the internal category field. `championship` is
    # what this family already carries when it is classified (production
    # 2026-09-17: the 141 resolved `pickleball` rows), so honouring the tag is
    # byte-identical to the answer those rows already hold, not a new shape.
    #
    # Like `table_tennis`, `pickleball` has no key in
    # `LLM_CATEGORY_TO_SPORT_PREFIX` and that is deliberate, not an omission to
    # be tidied later: `auto_create_sport_key_from_category` returns None on a
    # category with no prefix, so this cannot mint a `pickleball_other` event
    # for a sport we run no fixtures for. The category labels the card; it does
    # not open a matching rail.
    "pickleball",
    # #8507, for the same reason as the two above: a `Chess` tag must yield
    # ("championship", "chess"), which is what the resolved chess rows carry.
    "chess",
}


def _is_tradeable_opening(prob: Optional[float], has_trading: bool) -> bool:
    """Whether `prob` is a valid opening probability worth stamping.

    #137: an opening only makes sense at a real, tradeable, non-degenerate price.
    A price of exactly 0.0 or 1.0 is a settled/placeholder value, not an opening —
    stamping it on both sides of a decomposed Over/Under market produced the
    impossible both-sides=1.0 binaries that poisoned the calibration curve and the
    price_moved dimension. Requiring 0 < prob < 1 guarantees a binary's two sides
    can never both open at 1.0.
    """
    return bool(has_trading) and prob is not None and 0.0 < prob < 1.0


def sub_market_metadata(
    *,
    event_id,
    matchup_title: Optional[str],
    clob_token_ids: Optional[list] = None,
    content_understanding: Optional[dict] = None,
    venue_game_start=None,
    event_slug: Optional[str] = None,
) -> Optional[dict]:
    """``market_metadata`` for a decomposed Polymarket sub-market, at mint time.

    Queue 390 Item 2a, from ``C-INGEST-EID-AUDIT-1``. The sub-market loop used to
    build this inline as ``{"matchup_title": ...}`` or ``None``, throwing away an
    ``event.id`` that is in scope in the same iteration — the parent row two
    branches earlier stamps it from the same variable. Measured cost:
    **5,065 of 7,815 rows minted in 48h (64.8%) are bare-hex ``no_eid``**,
    ~2,500/day, and every reader of the canonical
    ``market_metadata->>'polymarket_event_id'`` path sees a miss on them and falls
    back to parsing ``group_id`` — a column that happens to contain the id, not a
    contract that promises it.

    Three rules, each of which a specimen in the test file depends on:

    * The key is **top level**. The census tests with jsonb ``?``, which does not
      see nested keys — the Ramírez specimen carries ``shape.container_group`` and
      is still counted ``no_eid``, correctly.
    * The value is a **string**, matching what ``group_id``'s
      ``split_part(...,':',2)`` yields, so the minted rows and the backfilled rows
      are comparable rather than merely both present.
    * A missing id stamps **nothing**. A placeholder would satisfy the census
      while pointing at nothing, turning a countable gap into an invisible one —
      which is the same mistake as gotcha #53, made on purpose.

    Returns ``None`` rather than ``{}`` when there is nothing to say: the caller
    passes this straight into the insert, and an empty object would overwrite
    populated metadata on re-ingest.

    ── ``clob_token_ids`` (Q460) ────────────────────────────────────────────

    The CLOB WebSocket subscribes by **asset id**, not by condition id, and
    ``_run_polymarket_ws_consumer`` reads those ids from exactly this key. They
    were never written. Measured on production 2026-08-30: of **687**
    live-or-starting-within-6h Polymarket markets, **0** carried
    ``clob_token_ids`` (or the camelCase spelling the consumer also accepts), so
    the consumer returned ``no_asset_ids`` and slept, every 60 seconds, forever.
    The Polymarket fast lane has never once streamed a price — which is why
    Alex's Hawaii @ Stanford card, whose blend carried Polymarket and nothing
    else, moved on a four-to-twenty-minute cadence.

    The Gamma payload has carried these ids the whole time;
    ``PolymarketAPIService`` already parses them into
    ``PolymarketMarket.clob_token_ids``. Nothing persisted them. Stamping them
    here is the whole unblock: the ingest re-serves open events continuously and
    the caller MERGES rather than clobbers, so live markets acquire the key on
    the next poll without a separate backfill.

    ── ``venue_game_start`` (#6073) ─────────────────────────────────────────

    The same class a third time: a value the loop is already holding, dropped on
    the way into the child row. The PARENT row two branches earlier stamps
    ``event.game_start_time`` (#4965's fixture instant) from this very variable;
    the sub-market got the matchup title and nothing else.

    That omission is not cosmetic, because **the sub-market is the row the event
    is minted from**. Measured on production 2026-09-14, group
    ``polymarket:1019271`` (ITF W50 Pazardzhik, Mazzola v Zeltina): the parent
    ``60980453`` holds ``venue_game_start = 2026-09-14T09:00:00Z`` and
    ``event_id`` NULL; its six children hold no ``venue_game_start`` at all and
    ``event_id = 15312430``. ``_create_event_from_prediction_market`` therefore dated
    that fixture from ``commence_time`` — Gamma's ``startDate``,
    ``2026-09-13 20:14:27Z``, the moment the market was LISTED — 12.8 hours
    before the match, so `/events/15312430` walked past its own invented kickoff
    into ``live`` and then ``suspended``, which the event page renders as "No
    result reported": a match that had not begun, reported as one that finished
    without a result. Three more specimens in #6073, each early by a different
    amount, which is what rules out a timezone constant.

    Stamped as an **ISO 8601 string**, matching what
    :func:`app.tasks.prediction_market_matching.venue_game_start` parses and what
    the parent already writes, so parent and child compare equal rather than
    merely both being present. A ``None`` stamps nothing and the reader fails
    open (its docstring says why), so a fixture the venue gives no start time for
    keeps exactly today's behaviour.
    """
    meta: dict = {}
    if matchup_title:
        meta["matchup_title"] = matchup_title
    if venue_game_start is not None:
        _vgs = (
            venue_game_start.isoformat()
            if hasattr(venue_game_start, "isoformat")
            else str(venue_game_start)
        )
        if _vgs:
            meta["venue_game_start"] = _vgs
    if event_id is not None and str(event_id) != "":
        meta["polymarket_event_id"] = str(event_id)
    if event_slug:
        # #8636: the slug's first token is the venue's league code (`clf` =
        # Club Friendlies). The sub-market is the row an event is minted from,
        # so the placement check reads it HERE, not on the parent.
        meta[POLYMARKET_EVENT_SLUG_KEY] = str(event_slug)
    if clob_token_ids:
        # Strings, always: Gamma returns these as decimal strings far wider than
        # a float64 can hold, and a token id that has been through a JSON number
        # is a token id that no longer subscribes to anything.
        meta["clob_token_ids"] = [str(t) for t in clob_token_ids if str(t)]
    if content_understanding:
        # ── CU-1 clause (2), #5273 ───────────────────────────────────────────
        #
        # What KIND of question this market asks, and whether Gamma's own
        # `sportsMarketType` corroborates it. Clause (4) taught the DTO to
        # retain that label; it was persisted NOWHERE, so the one place both
        # signals are in hand at once is right here, in the ingest loop that
        # already holds the parsed market.
        #
        # Stamped through the same merge the caller uses for every other key,
        # which is the whole reason no backfill is needed: Polymarket re-serves
        # open events continuously, so live rows ACQUIRE the understanding on
        # the next poll and a re-ingest refreshes one that has gone stale
        # because the venue relabelled the market.
        meta[CONTENT_UNDERSTANDING_KEY] = content_understanding
    return meta or None


def parent_venue_market_type(event) -> Optional[str]:
    """Gamma's ``sportsMarketType`` for the PARENT row, or ``None`` (#5273).

    A parent covers one market or many, so the venue's label for it is the label
    its markets AGREE on. One market: that market's label. Several that agree
    (the negrisk game group — three "will X win" legs of one question): the
    shared value. Several that disagree, or any that is missing: ``None``, which
    `build_content_understanding` records as UNCONFIRMED.

    🔴 Disagreement must read as ABSENCE, never as a pick. Choosing the first
    child's label, or the modal one, would put a venue claim on the parent that
    the venue did not make about it — and `agreement` would then be a comparison
    against something we invented, which is worse than no comparison at all.
    Absence is not evidence (it is 21% of the population); a fabricated label is.
    """
    labels = {
        getattr(market, "sports_market_type", None)
        for market in (getattr(event, "markets", None) or [])
    }
    if len(labels) != 1:
        return None
    return labels.pop()


def parent_content_understanding(event, *, sport: Optional[str] = None) -> Optional[dict]:
    """The understanding for an event's PARENT row (#5273).

    🔴 CERT-2733's repair. `sub_market_metadata` above types the decomposed
    children, and that was the whole of clause (2) — but the parent is a priced
    row in EVERY shape: `_parent_outcome_data(event)` runs before the
    decomposition branch, so the parent always carries outcomes, and for the two
    shapes that never decompose it is the only row there is. Sub-markets are
    written only when ``not event.neg_risk and len(event.markets) > 1``, so:

      * **one market** — the parent IS the market (13,956 rows, 1,750 open,
        measured 2026-09-12). Gamma serves the shape live: event `1007524`,
        `PPA - Women's Singles: Hannah Blatt vs Polina Libo`, active,
        non-neg-risk, one market, `sportsMarketType=moneyline`.
      * **negrisk** — the legs are flattened onto the parent, which is therefore
        the row that speaks for the match winner (67,855 rows, 9,340 open).
        `AFC Bournemouth vs. Brentford FC` with `[Bournemouth, Brentford, Draw]`
        is one of them, and it is the row the blend read on 2026-09-12.
      * **decomposed** — the children carry their own and the parent is the
        group anchor, but it still holds outcomes and is still judged by
        `admissible_as_blend_speaker`, so recording our reading of it is honest
        and leaving it blank is not.

    Every one of those went through the typed path and came out untyped, on
    every poll, forever, because the poll is the only writer.

    TYPED ON THE ROW'S OWN NAME, which for a parent is `event.title` and not any
    market's `question`. The same rule the sub-market path follows for the
    opposite reason: the stored type must describe the row a reader sees and the
    row `admissible_as_blend_speaker` judges, and for this row that string is
    the event title.

    Returns ``None`` when there is nothing to say — no title, or no markets at
    all — so the caller stamps no key and a re-ingest cannot overwrite a
    populated one with an empty object (`sub_market_metadata`'s own rule, for
    the same reason).
    """
    if not (getattr(event, "markets", None) or []):
        return None
    return build_content_understanding(
        name=getattr(event, "title", None),
        external_id=getattr(event, "id", None),
        sport=sport,
        sports_market_type=parent_venue_market_type(event),
    )


def stamp_parent_content_understanding(
    metadata: dict, event, *, sport: Optional[str] = None
) -> dict:
    """Stamp the parent's understanding into ``metadata``, or leave it alone.

    The guard lives here rather than at the call site so that "a row with
    nothing to say carries NO KEY" is a tested property instead of an ``if`` in
    the middle of a 200-line ingest block. It is load-bearing twice over: the
    census idiom for this key is jsonb ``?``, which sees a key holding JSON
    ``null`` and counts the row as understood; and the parent write REPLACES
    ``market_metadata`` wholesale, so a stamped null would also erase a good
    understanding written by the poll before it.
    """
    understanding = parent_content_understanding(event, sport=sport)
    if understanding:
        metadata[CONTENT_UNDERSTANDING_KEY] = understanding
    return metadata


# Tags that name the FORM of a market, or a whole shelf of them, rather than its
# SUBJECT. #7874: `_tags_to_category` returns on the first tag it recognises and
# Polymarket lists tags in its own order, so a market's category was decided by
# whichever of its tags the venue happened to print first. Read off Gamma
# 2026-09-22, event 60182 "Nobel Peace Prize Winner 2026" is tagged
#
#     Awards, Politics, Geopolitics, World
#
# — `awards` maps to `entertainment`, so a field of humanitarian organisations
# and dissidents wore a film clapperboard on page one while the three tags that
# name its actual subject sat unread behind it. Nothing about the market was
# ambiguous; the venue had said "Politics" out loud and position alone buried it.
#
# A weak tag is not ignored — it still decides the category when it is all a
# market has, so an Oscars event tagged only `Awards` is still `entertainment`.
# It just stops OUTRANKING a tag that names a subject.
#
# WHY EACH MEMBER IS IN. Replayed over the venue's own listings for
# all 289 distinct Polymarket events behind our open `entertainment` markets
# (2026-09-22, `artifacts/d394-7874/`), `awards` moves TWO of them and both are
# unambiguous:
#
#     60182   Nobel Peace Prize Winner 2026   entertainment -> politics
#     994443  Golden Boy 2026 Winner          entertainment -> soccer
#
# Golden Boy is a football award and #7874's own issue text had listed it as
# genuinely entertainment; the venue tags it `Awards, Soccer, Sports`.
#
# `culture` JOINED THIS SET IN #7914, after the three landings that held it out
# were re-derived through the whole cascade instead of the tag map alone.
#
# #7874 held it out because demoting it moves 40 more events and three of them
# looked wrong: two Ebola markets to `weather`, and France's hottest-summer
# market to `tech`. Replayed over the SAME banked 42 rows with
# `resolve_event_category` imported rather than `_tags_to_category` alone
# (`artifacts/d396-7914/rederive_culture_cascade.py`), two of those three were
# already handled by machinery that shipped long ago: arm 4 runs
# `misfiled_subject` AFTER the tag map, `weather` is one of its epidemiology
# sources since #4264, and `ebola` is in the pattern — so both Ebola events land
# on `health`, which is the shelf #7914 said they belonged on. The tag map was
# imported; the CASCADE AROUND IT WAS NOT, and that is the whole reason the
# earlier sizing was wrong by two of three.
#
# The surviving one — France — is fixed in the same ship by the climate-record
# arm of `_WEATHER_HAZARD_RE`, so no subject-tag ordering rule is needed after
# all.
#
# 🪤 WHAT THE CLASSIFIER RETURNS IS NOT WHAT A READER GETS, AND THE GAP IS
# MEASURED HERE RATHER THAN ASSUMED (CERT-3271 blocked the first presentation of
# this change for claiming otherwise). A row only takes a new category when the
# poller next WRITES it. Of the 42 events in the cohort, measured on production
# 2026-09-22 03:15Z:
#
#     33 events / 76 open markets   written within 14 days -> these move
#      9 events /  9 open markets   not written in 19-40 days -> these DO NOT
#
# The nine are #7930 and are three different defects, none of them `archived`:
# four are ABSENT from the venue's `/events?id=` (the Brazil election rows), two
# are `closed=true` at the venue while we serve them open (Tupac; Brazil Vice
# Governor), and three are `active=true, closed=false, archived=false` but
# LOW-VOLUME (France 1,715, Ebola-844717 359, Banksy 1,426) and so fall off the
# tail of a volume-ordered scan. That last shape is a coverage defect and is not
# repairable by anything aimed at inactive or archived rows.
#
# So France — the row half 2 was written for — does not move until #7930 lands.
# Half 2 is still not inert: `Where will 2026 rank among the hottest years on
# record?` (event 79905) moves from the `tech` shelf when its writer next runs.
#
# 🪤 THAT WRITER IS THE HOURLY HEAVY `recover_sunk_polymarket_events`, NOT THE
# ORDINARY POLL, AND THE FIRST PRESENTATION OF THIS COMMENT SAID OTHERWISE.
# `poll_polymarket_markets` is not in `HEAVY_TASKS`, which is the rule's home;
# the question that matters is which scheduled task REWRITES THE ROW. Measured
# on production 2026-09-22 04:10Z, both this row (market 113358) and #7874's
# Nobel row (113129) carry `volume_updated_at` stamped 19:26:52Z / 19:27:03Z —
# the `crontab(minute=26)` recovery sweep's signature, nine hours after the
# :15 poll had last had its chance at them. Both match the recovery selector
# (`_SUNK_POLY_WHERE`): polymarket, `status='open'`, a parent id, and
# `volume_updated_at` older than `SUNK_POLY_STALE_HOURS`.
#
# The consequence for anyone paying an after-check on a row like this: it is
# not hourly. Both sit in the ROTATE arm (resolution beyond the 14-day
# imminent horizon), which walks 9,526 eligible rows 300 at a time behind a
# cursor — a ~32-hour lap. They are reached in the first pass after the cursor
# WRAPS, because only 120 and 223 eligible rows sort below them. A row still
# reading its old category is the expected state for most of that lap; read
# `volume_updated_at`, not the clock, before calling anything a regression.
#
# With both halves in place the 40 classifier moves read:
#
#     27  -> politics    17 plainly civic (5 Brazil election rows, the Mangione
#                        trial, Hasan Piker arrested), 10 mention/tweet-volume
#     6   -> tech        Doge-1, Millennium Prize, GTA 6 ... (France now weather)
#     2   -> esports     Deadlock's release, MoistCr1TiKaL
#     2   -> culture     Banksy on Instagram, Nara Smith
#     2   -> health      both Ebola events, via arm 4
#     1   -> economics   Costco's hotdog price
#
# THE ONE JUDGEMENT CALL, MADE DELIBERATELY: the 10 `Elon Musk # tweets` /
# `Joe Rogan mentions` / `NYT front-page headlines` rows land on `politics`.
# #7914 called this arguable and it is. It ships because the venue itself tags
# every one of them `Politics`, because `entertainment` is not the more correct
# answer, and because the risk it was held against was MEASURED rather than
# assumed: those 10 events are 36 open markets against the politics shelf's
# 7,422 (0.5%), their best `market_tier` is 2 where the shelf's is 1, and their
# top 24h volume is 462,974 against the shelf's 3,976,818. They cannot headline
# the page, and `/politics` renders every section at its cap out of pools in the
# hundreds to thousands, so they displace nothing. Whether a mention/volume
# market deserves a shelf of its own is a product question, filed separately
# rather than answered by a tag map.
#
# `world`, `news` and `global` are the map's other "Broad catch-alls" and were in
# this set too. They move ZERO events. An entry that changes nothing is not a
# conservative choice, it is an unmeasured claim, so they are out.
#
# Note what this is NOT. Remapping `awards` to `politics` would badge the Oscars
# as politics; dropping the weak tag would drop an awards-only market to `other`.
# Both are caught by the controls in
# `tests/test_polymarket_awards_tag_precedence_7874.py`.
#
# The map already carries a `"nobel": "culture"` key and it is dead code for this
# market: the keys are matched EXACTLY against tag labels, the venue tags this
# event `Awards`, and no Polymarket tag is labelled "Nobel". A fix that leaned on
# that key would have been inert — the tag the reader's badge came from is the
# one the payload actually carries.
_WEAK_TAGS = frozenset({"awards", "culture"})


def _tags_to_category(tags: list[str]) -> tuple[str, Optional[str]]:
    """
    Map Polymarket tags to (internal_category, llm_sport_category).

    Subject tags outrank the `_WEAK_TAGS` catch-alls no matter what order the
    venue listed them in; within each of those two ranks, payload order still
    breaks the tie.

    Returns:
        Tuple of (category for FuturesMarket.category, llm_sport_category)
    """
    # Two passes over the venue's list rather than one pass over a re-sorted
    # copy: sorting would also reorder the tags WITHIN each rank, and first-one-
    # wins among equally specific tags is the behaviour every existing caller
    # already depends on.
    for allow_weak in (False, True):
        for tag in tags:
            tag_lower = tag.lower().strip()
            if tag_lower not in _TAG_TO_CATEGORY:
                continue
            if not allow_weak and tag_lower in _WEAK_TAGS:
                continue
            mapped = _TAG_TO_CATEGORY[tag_lower]
            if mapped in _SPORT_CATEGORIES:
                return "championship", mapped
            else:
                return mapped, mapped

    # If "Sports" tag is present but no specific sport matched
    for tag in tags:
        if tag.lower().strip() == "sports":
            return "championship", None

    return "other", None


# `NON_SPORT_CATEGORIES` — the set that must never flip a market to
# `category="championship"` — used to be defined here. Named once: it had already
# been de-duplicated out of the poller loop's function body, which was "a copy
# waiting to disagree with the one above it". #7814 gave it a second reader
# outside this module (the taxonomy reconcile arm asks the same question of the
# same column), so the definition moved to `app.utils.event_taxonomy` beside the
# tag vocabulary it is read against. Imported at the top of this file; a second
# module-level copy would be the same defect one import further out.


def resolve_event_category(
    category: str,
    llm_sport_category: Optional[str],
    title: Optional[str],
    group_names: list[str],
) -> tuple[str, Optional[str], str]:
    """The rest of the category cascade, after the tags have had their say.

    Takes `_tags_to_category`'s answer and the event's titles, and returns
    `(category, llm_sport_category, arm)` — the two values the writer will store,
    plus which arm decided them. The caller needs the arm because
    `stats["by_category"]` counts the FALLBACK arm only, and that has been its
    meaning since before the extraction; returning it is cheaper and more honest
    than the caller re-deriving the condition and calling
    `detect_table_tennis_group` a second time.

    Four arms, in order — each one only allowed to act when the arms above it
    did not:

      1. TABLE TENNIS at the group level (#1230). Setka/TT-Cup matches have a bare
         "Player vs. Player" parent title that `categorize_by_rules` routes to
         baseball via summer seasonal inference; their child props carry the
         unambiguous "Total Games O/U N" tell. Must run before the baseball
         fallback below.
      2. NO USABLE TAG -> pattern match, then league inference.
      3. A NON-SPORT TAG BUT A SPORT TITLE -> promote ("Pro Baseball: 2026 AL Cy
         Young Winner", tagged `awards`).
      4. A NON-SPORT TAG ON THE WRONG NON-SPORT SHELF -> `misfiled_subject`.

    EXTRACTED FROM THE POLLER LOOP (Q446) so arm 4 could be tested against arms 1-3
    rather than in isolation from them. Ordering is the whole substance of this
    cascade and it was only reachable by running a 200-line async loop with a live
    database, which is why the loop had grown four inline arms that no test drove.
    Behaviour is unchanged for arms 1-3; `tests/test_polymarket_category_cascade.py`
    pins the order.
    """
    from app.utils.futures_categorization import (
        categorize_by_rules,
        detect_league as _detect_league,
        detect_table_tennis_group,
        infer_sport_from_league as _infer,
        misfiled_subject,
    )

    _NON_SPORT = NON_SPORT_CATEGORIES
    # `categorize_by_rules` and `detect_league` both regex the raw string and raise
    # TypeError on None. The poller has always passed `event.title` straight in, so
    # a titleless event would have taken the whole batch's `except` — visible only as
    # a swallowed error count. Normalising here rather than at each call site.
    title = title or ""

    # 1 — table tennis, at the group level, before anything can guess baseball.
    # Q493: only when the tags said nothing usable — which is arm 1's own stated
    # precondition. Its whole justification is that a Setka parent title is a bare
    # "Player vs. Player" with no sport keyword AND no usable tag, so the fallback
    # would guess baseball. When Polymarket has already named the sport, there is
    # nothing to rescue and this heuristic must not overrule it: a real US Open
    # match tagged "Tennis" carries per-SET games props ("Set 1 Games O/U 8.5")
    # whose totals sit below the table-tennis threshold, so the unguarded arm
    # relabelled the entire main draw `table_tennis`.
    if not llm_sport_category or llm_sport_category == "other":
        if detect_table_tennis_group(group_names):
            return "championship", "table_tennis", "table_tennis"

    # 2 — the tags said nothing usable.
    if not llm_sport_category or llm_sport_category == "other":
        rules_result = categorize_by_rules(title)
        if rules_result:
            llm_sport_category = rules_result
        else:
            _league = _detect_league(title)
            if _league:
                _sport = _infer(_league)
                if _sport:
                    llm_sport_category = _sport
        if llm_sport_category and llm_sport_category not in _NON_SPORT:
            category = "championship"
        return category, llm_sport_category, "fallback"

    # 3 — a non-sport tag on a market whose title clearly names a sport.
    if llm_sport_category in _NON_SPORT:
        rules_result = categorize_by_rules(title)
        if rules_result and rules_result not in _NON_SPORT:
            return "championship", rules_result, "promoted"
        _league = _detect_league(title)
        if _league:
            _sport = _infer(_league)
            if _sport and _sport not in _NON_SPORT:
                return "championship", _sport, "promoted"

        # 4 — Q446 / CAL-P132. The venue named a real non-sport shelf and it is the
        # wrong one: 104 markets carry `tech` while being flu hospitalization rates,
        # measles counts and wildfire acreage. There is no tag to remap — Polymarket
        # tags "Flu Hospitalization Rate Week 10" `tech` and nothing else — so the
        # title is the only place the subject is written down. LAST, so no sport can
        # ever lose a market to it.
        subject = misfiled_subject(title, llm_sport_category)
        if subject:
            return subject, subject, "subject"

    return category, llm_sport_category, "tag"


# =========================================================================
# Polling implementation
# =========================================================================

async def _poll_polymarket_markets():
    """Async implementation of Polymarket polling."""
    import asyncio
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.odds_math import probability_to_american
    from app.utils.market_label_normalization import compute_market_tier
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    service = PolymarketAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "legs_retired": 0,  # #4000: prices withdrawn because the venue quotes none
        # #2027: seeded at zero so a quiet poll and a poll that never asked
        # read differently. The refusal is the ship; the count is how anyone
        # tells that it happened without opening the database.
        "opening_refused_hindsight": 0,
        "errors": [],
        "by_category": {},
        "crypto_skipped": 0,
        "total_api_events": 0,
    }

    BATCH_SIZE = 50  # Commit every N events to limit memory

    try:
        # One-time cleanup: delete orphan outcomes with NULL external_id
        try:
            async with get_task_session() as session:
                from sqlalchemy import delete as sa_delete
                from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
                orphan_sub = select(FuturesOutcome.id).where(
                    FuturesOutcome.external_id.is_(None),
                    FuturesOutcome.market_id.in_(
                        select(FuturesMarket.id).where(
                            FuturesMarket.source == "polymarket"
                        )
                    ),
                )
                orphan_ids = (await session.execute(orphan_sub)).scalars().all()
                if orphan_ids:
                    logger.info("Cleanup: deleting %d Polymarket orphan outcomes with NULL external_id", len(orphan_ids))
                    await session.execute(
                        sa_delete(FuturesOddsSnapshot).where(
                            FuturesOddsSnapshot.outcome_id.in_(orphan_ids)
                        )
                    )
                    await session.execute(
                        sa_delete(FuturesOutcome).where(
                            FuturesOutcome.id.in_(orphan_ids)
                        )
                    )
                    await session.commit()
                    logger.info("Polymarket orphan cleanup complete: %d deleted", len(orphan_ids))
        except Exception as e:
            logger.warning("Polymarket orphan cleanup failed (non-fatal): %s", e)

        # Cleanup: delete anonymized "Player XX" reserved-slot outcomes (#953).
        # Polymarket pre-creates empty slots named "Player AD"/"Player AG" with no
        # recoverable name (verified in the raw payload: groupItemTitle="Player AD",
        # prices=None, bid=0, lastTrade=0). The broadened _is_placeholder_outcome
        # now skips them at ingestion, but rows ingested before that fix persist and
        # render at ~0.5 across ~44 award/round-leader markets. Remove them so they
        # stop surfacing everywhere (idempotent — re-runs find none; real named
        # candidates in the same markets are untouched). Display fix only; these are
        # OPEN, unresolved, NULL cal_prob/volume rows — not an is_winner mutation
        # (gotcha #21).
        try:
            async with get_task_session() as session:
                from sqlalchemy import delete as sa_delete
                from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
                # Scope to OPEN/active markets only: that is where placeholders
                # render, and it keeps the cleanup away from resolved-market rows
                # (gotcha #21 — never disturb settled data).
                placeholder_sub = select(FuturesOutcome.id).where(
                    FuturesOutcome.name.op("~")(r"^Player [A-Z]+$"),
                    FuturesOutcome.market_id.in_(
                        select(FuturesMarket.id).where(
                            FuturesMarket.source == "polymarket",
                            FuturesMarket.status.in_(["open", "active"]),
                        )
                    ),
                )
                placeholder_ids = (await session.execute(placeholder_sub)).scalars().all()
                if placeholder_ids:
                    logger.info(
                        "Cleanup: deleting %d Polymarket 'Player XX' placeholder outcomes (#953)",
                        len(placeholder_ids),
                    )
                    await session.execute(
                        sa_delete(FuturesOddsSnapshot).where(
                            FuturesOddsSnapshot.outcome_id.in_(placeholder_ids)
                        )
                    )
                    await session.execute(
                        sa_delete(FuturesOutcome).where(
                            FuturesOutcome.id.in_(placeholder_ids)
                        )
                    )
                    await session.commit()
                    logger.info(
                        "Polymarket placeholder cleanup complete: %d deleted",
                        len(placeholder_ids),
                    )
        except Exception as e:
            logger.warning("Polymarket placeholder cleanup failed (non-fatal): %s", e)

        # Stream events page-by-page instead of loading all into memory.
        # Each page is processed and committed in batches.
        #
        # #219E (creation freeze, poly edition): Polymarket's Gamma API changed
        # (~2026-07-14) to CAP offset pagination at offset 2000 — offset>=2100
        # now returns HTTP 422 "offset too large, use /events/keyset". Combined
        # with the previous default sort (oldest-first by id), the poll was stuck
        # perpetually re-scanning the OLDEST ~2000 active events (all already in
        # DB) and could NEVER reach newly-created markets → daily creation fell
        # off a cliff from ~1000-2000/day to <10/day while the poll kept
        # SUCCEEDING (it just re-updated the same old set). Fix: order the scan
        # NEWEST-first (order=startDate desc, below) so new markets land on the
        # first pages, and bound max_pages to the 2000-offset cap so we never
        # burn calls on the guaranteed-422 tail. Durable follow-up: migrate to
        # /events/keyset for uncapped coverage (see #219E report).
        max_pages = 20  # offset 0..1900 — the Gamma offset-2000 hard cap
        seen_ids: set[str] = set()
        batch: list = []

        # #984: bound the pagination to a time budget under the 540s soft limit.
        # poll_polymarket scanned up to 130 active pages + an 80-page settled-
        # sports pass with NO time guard, busting the wall (consec=13, 0
        # successes >24h — the sole driver of critical health). Mirror the #969
        # inner-bound: a per-page budget check breaks before the wall, and a
        # rotating Redis page cursor resumes next run so coverage rotates across
        # runs instead of re-scanning the same early pages each time.
        import time as _time
        _start = _time.monotonic()
        _MAX_SECONDS = 420  # 120s margin under the 540s soft limit
        from app.tasks.redis_state import get_redis_client
        _rc = get_redis_client()
        _poll_cursor_key = "bainluck:polymarket_poll_page"
        _resume_page = int(_rc.get(_poll_cursor_key) or 0)
        if not (0 <= _resume_page < max_pages):
            _resume_page = 0

        events_data = None
        pages_fetched = 0
        budget_hit = False
        for _i in range(max_pages):
            page = (_resume_page + _i) % max_pages
            if _time.monotonic() - _start > _MAX_SECONDS:
                _rc.setex(_poll_cursor_key, 86400, str(page))  # resume here next run
                logger.info(
                    "Polymarket poll: time budget (%ds) hit after %d pages "
                    "(resume page %d next run)", _MAX_SECONDS, _i, page,
                )
                budget_hit = True
                break
            if _i > 0:
                await asyncio.sleep(0.3)

            try:
                # #219E: NEWEST-first. The Gamma default sort is oldest-first,
                # which — under the new offset-2000 cap — pinned the poll on the
                # oldest (already-ingested) active events and created nothing.
                # order=startDate + ascending=False puts newly-created markets on
                # the first pages, well inside the 2000-offset window.
                events_data = await service.get_events(
                    active=True, closed=False, limit=100, offset=page * 100,
                    order="startDate", ascending=False,
                )
            except Exception as e:
                logger.warning("Error fetching Polymarket page %d: %s", page, e)
                # #219E: a 422 "offset too large" means we hit the Gamma cap —
                # reset the cursor so the next run restarts at the newest page
                # instead of sticking at an always-422 offset.
                if "offset too large" in str(e) or "422" in str(e):
                    _rc.setex(_poll_cursor_key, 86400, "0")
                break

            pages_fetched += 1
            if not events_data:
                # wrapped past the end of the active set — reset cursor, stop
                _rc.setex(_poll_cursor_key, 86400, "0")
                break

            for event_data in events_data:
                event_id = str(event_data.get("id", ""))
                if not event_id or event_id in seen_ids:
                    continue
                seen_ids.add(event_id)

                parsed = service._parse_event(event_data)
                if parsed and parsed.markets:
                    batch.append(parsed)

                # Process batch when full
                if len(batch) >= BATCH_SIZE:
                    await _process_event_batch(
                        batch, stats, FuturesMarket, FuturesOutcome,
                        FuturesOddsSnapshot, pg_insert, probability_to_american,
                        compute_market_tier,
                    )
                    batch.clear()

            if len(events_data) < 100:
                # reached the last active page — next run starts fresh
                _rc.setex(_poll_cursor_key, 86400, "0")
                break
        else:
            # full max_pages sweep with no early break — reset cursor
            _rc.setex(_poll_cursor_key, 86400, "0")

        # Process remaining events
        if batch:
            await _process_event_batch(
                batch, stats, FuturesMarket, FuturesOutcome,
                FuturesOddsSnapshot, pg_insert, probability_to_american,
                compute_market_tier,
            )
            batch.clear()

        logger.info(
            "Polymarket: fetched %d unique events across %d pages (budget_hit=%s)",
            len(seen_ids), pages_fetched, budget_hit,
        )
        if pages_fetched >= max_pages:
            logger.warning(
                "Polymarket: hit page cap (%d). There may be more events — "
                "consider raising max_pages.",
                max_pages,
            )

        stats["pages_fetched"] = pages_fetched
        stats["unique_events_seen"] = len(seen_ids)
        stats["hit_page_cap"] = pages_fetched >= max_pages

        # Supplementary pass: fetch settled sports game events by tag.
        # The main scan (active=True, closed=False) only gets open events.
        # Settled game events are needed for source coverage + calibration.
        # #173/#1024: mma/boxing were absent, so a poly fight event the main scan
        # missed while open (e.g. a budget-truncated cycle) could NEVER be
        # recovered — the poly half of A5's combat cross-source blend. Confirmed
        # live: gamma tag_slug=mma / =boxing return settled UFC/boxing events.
        # The pass is budget-guarded (per-tag + per-page `_MAX_SECONDS` breaks),
        # so extending the tag list can't push the task past the 540s wall.
        #
        # #174 Item 2: CATEGORY-AGNOSTIC. A hand list is the "hand-built net has
        # holes" class (golf-class → combat-class, same bug rediscovered). Enumerate
        # tags from the SOURCE (`get_tags`) minus crypto, keep the proven sports tags
        # as a PRIORITY head (never regress), and rotate the remainder through a
        # resumable cursor so any category is reached within a few runs and per-run
        # work stays bounded (gotcha #34). Fallback-safe: any enumeration failure
        # falls back to the hand list, so behavior can only ever improve, never break.
        _PRIORITY_TAG_SLUGS = [
            "baseball", "basketball", "hockey", "football", "mma", "boxing",
        ]
        _TAGS_PER_RUN = 14  # priority(6) + ~8 rotated; well within _MAX_SECONDS
        _tag_cursor_key = "bainluck:poly_settled_tag_cursor"
        try:
            from app.utils.settled_recovery import extract_tag_slugs, select_rotation

            _all_tags = extract_tag_slugs(await service.get_tags(limit=200))
            if _all_tags:
                _cursor_pos = int(_rc.get(_tag_cursor_key) or 0)
                _SPORTS_TAG_SLUGS, _next_pos = select_rotation(
                    _all_tags, _PRIORITY_TAG_SLUGS, _cursor_pos, _TAGS_PER_RUN
                )
                _rc.setex(_tag_cursor_key, 86400 * 14, str(_next_pos))
                logger.info(
                    "Polymarket settled-recovery: %d tags at source, scanning %d "
                    "this run (priority + rotated from %d)",
                    len(_all_tags), len(_SPORTS_TAG_SLUGS), _cursor_pos,
                )
            else:
                _SPORTS_TAG_SLUGS = _PRIORITY_TAG_SLUGS
        except Exception as _tag_err:
            logger.warning(
                "Polymarket tag enumeration failed (%s) — falling back to hand list",
                _tag_err,
            )
            _SPORTS_TAG_SLUGS = _PRIORITY_TAG_SLUGS
        supplemented = 0
        for tag_slug in _SPORTS_TAG_SLUGS:
            # #984: skip the settled-sports pass entirely if the main scan already
            # spent the budget — it must not push the task past the 540s wall.
            if budget_hit or (_time.monotonic() - _start) > _MAX_SECONDS:
                budget_hit = True
                break
            tag_offset = 0
            max_tag_pages = 20
            for _tp in range(max_tag_pages):
                if (_time.monotonic() - _start) > _MAX_SECONDS:
                    budget_hit = True
                    break
                try:
                    await asyncio.sleep(0.3)
                    tag_events = await service.get_events(
                        active=None,
                        closed=True,
                        tag_slug=tag_slug,
                        limit=100,
                        offset=tag_offset,
                        order="startDate",
                        ascending=False,
                    )
                    if not tag_events:
                        break
                    for event_data in tag_events:
                        eid = str(event_data.get("id", ""))
                        if eid in seen_ids:
                            continue
                        seen_ids.add(eid)
                        parsed = service._parse_event(event_data)
                        if parsed and parsed.markets:
                            batch.append(parsed)
                            supplemented += 1
                    if batch:
                        await _process_event_batch(
                            batch, stats, FuturesMarket, FuturesOutcome,
                            FuturesOddsSnapshot, pg_insert, probability_to_american,
                            compute_market_tier,
                        )
                        batch.clear()
                    tag_offset += 100
                    if len(tag_events) < 100:
                        break
                except Exception as e:
                    logger.debug("Polymarket supplementary %s page %d: %s", tag_slug, _tp, e)
                    break
        if supplemented:
            logger.info("Polymarket supplementary sports fetch added %d events", supplemented)

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    # ONE sweep for the whole poll, deliberately placed AFTER the `finally` so a
    # top-level error (already recorded above) still gets its links written —
    # per-batch, a raising poll kept whatever the completed batches had swept, and
    # this must not be weaker than that. `stats` is reported either way.
    stats["sub_markets_linked"] = await link_polymarket_sub_markets()

    # #6073, AFTER the link sweep and for the same reason it sits after the
    # `finally`: it reads `event_id` on the child rows that sweep has just
    # written, so running it earlier would scan a corpus missing exactly the rows
    # this poll repaired. Its own failure must not cost the poll its stats.
    try:
        stats["redated_events"] = await redate_polymarket_listing_stamped_events()
    except Exception as e:  # noqa: BLE001 - one repair must not fail a whole poll
        stats["errors"].append(f"redate: {e}")
        logger.exception("Polymarket re-date sweep (#6073) failed")

    # #6073's last gap, and it runs AFTER the sweep above deliberately. The two
    # are independent — this one is keyed on the row's own contradiction, not on
    # either writer — but the sweep can itself produce a row this band covers if
    # its status arm is ever skipped, and a drain that runs BEFORE its likeliest
    # producer waits a whole poll to see the row. Its own try/except for the same
    # reason the sweep has one: one repair must not cost the poll its stats.
    try:
        stats["stuck_future_status"] = await rescue_stuck_future_status_events()
    except Exception as e:  # noqa: BLE001 - one repair must not fail a whole poll
        stats["errors"].append(f"stuck_status: {e}")
        logger.exception("Stuck-status rescue (#6073) failed")

    stats["total_api_events"] = len(seen_ids)
    logger.info(
        "Polymarket poll: %d API events → %d processed, %d markets, %d outcomes, %d snapshots, %d crypto skipped, %d openings refused as hindsight (#2027), %d errors | by_category: %s",
        stats["total_api_events"], stats["events_processed"], stats["markets_processed"],
        stats["outcomes_updated"], stats["snapshots_created"], stats["crypto_skipped"],
        stats.get("opening_refused_hindsight", 0),
        len(stats["errors"]), stats["by_category"],
    )
    return stats


#: The parent→sub-market ``event_id`` sweep, as ONE statement per poll.
#:
#: Kept at module scope, and public, so a guard can execute it without driving a
#: whole poll — the class of bug this queue exists to avoid is a fix that sits
#: behind a helper no test ever runs (LAT-P159/CERT-523).
LINK_SUB_MARKETS_SQL = """
    UPDATE futures_markets sub
    SET event_id = parent.event_id
    FROM futures_markets parent
    WHERE sub.group_type = 'polymarket_sub_market'
      AND sub.event_id IS NULL
      AND sub.group_id IS NOT NULL
      AND parent.source = 'polymarket'
      AND parent.group_type = 'polymarket_event'
      AND parent.group_id = sub.group_id
      AND parent.event_id IS NOT NULL
"""


async def link_polymarket_sub_markets() -> int:
    """Propagate ``event_id`` from parent Polymarket markets to their sub-markets.

    The matching task links parent game markets (e.g. "Magic vs. Pistons") to
    events; sub-markets (player props, spreads) inherit that link via ``group_id``.

    WHY THIS IS ONE CALL PER POLL AND NOT ONE PER BATCH
    ---------------------------------------------------
    It used to run at the end of ``_process_event_batch``, so it fired once per 50
    events. Measured on production 2026-08-31 from ``pg_stat_statements`` (age
    77 d 9:57, so 1,858 hourly polls):

    * **83,631 calls** — 45.0 per poll, exactly ``BATCH_SIZE``-shaped
    * **189,625,725 ms total** (52.7 hours), mean **2,267 ms**, max **125,417 ms**
    * **3,005,544,566 shared blocks read** — ``20.04 %`` of ALL disk reads in the
      database, the single largest consumer, from ``0.001 %`` of its calls
    * **15,686 rows written in total** — 0.19 per call, 8.4 per poll

    Its predicate is entirely global: it names no batch state, so each of the 45
    calls re-scanned the same corpus. The cost is dominated by rows it can never
    write — 242,891 unlinked sub-markets carrying a ``group_id`` whose parent has
    no ``event_id``, rescanned 45 times an hour, 1,080 times a day.

    EQUIVALENCE. Running it once after the last batch leaves the same rows set:

    1. The predicate reads only committed table state, never the batch.
    2. ``seen_ids`` dedups events across the whole poll, so a given sub-market is
       upserted at most ONCE per poll — no later batch can re-null an ``event_id``
       an earlier sweep wrote. (The upsert used to write ``event_id`` including
       NULL, which is why this needed checking rather than assuming; since
       #8430 it writes only a parent's non-NULL link.)
    3. So the final sweep observes every write the poll made, and the union of
       what the intermediate sweeps could have written is a subset of it.

    THE ONE BEHAVIOURAL DIFFERENCE, STATED. If the worker is SIGKILLed mid-poll
    (no Python unwind), this sweep does not run at all, where per-batch would have
    committed the completed batches' links. That is why the call site sits after
    the top-level ``finally`` — every failure that unwinds still sweeps. It is
    also the condition this change makes rarer: the poll's p95 duration is
    459,001 ms against a 540 s soft limit (85 %), and the ~102 s/poll this
    statement costs is 22 % of that runtime. The sweep is idempotent, so a genuinely
    killed poll loses nothing the next one will not pick up.

    Returns the number of sub-markets linked.
    """
    from sqlalchemy import text as _text

    async with get_task_session() as session:
        result = await session.execute(_text(LINK_SUB_MARKETS_SQL))
        await session.commit()
        return result.rowcount or 0


# ── #6073: re-date the fixtures ALREADY minted from the listing stamp ─────────
#
# The other two halves of #6073 are PREVENTION and they only reach a mint:
# `sub_market_metadata` stamps `venue_game_start` on the child row (this module),
# and `auto_create_commence_time` prefers it when it dates a NEW event (lane1's
# `a02aca00a`). Neither re-dates a row that already exists, and
# `commence_time_write_authorized` cannot: `_SOURCE_PRIORITY` ranks
# `polymarket_venue` and `polymarket` equally (deliberately — same provider, same
# authority), a tie loses, and the `same_record_revision` path needs
# `incoming_source == current_source`, which a row stamped plain `polymarket`
# fails. So the standing population is unreachable by design and needs its own
# rail. This is it — CERT-2826's named repair.
#
# MEASURED ON PRODUCTION, 2026-09-14 (the whole band, not a sample):
#
#     events with commence_time_source='polymarket'      25,079
#       ├─ closed                                        17,633   not touched
#       ├─ voided                                         6,261   not touched
#       ├─ suspended                                      1,175 ┐ the reader-visible
#       └─ live                                              10 ┘ band
#     of that band, still holding a linked Polymarket market    827
#       ├─ group carries a venue_game_start                     820
#       └─ no stamp anywhere in the group                         7   skipped
#     of the 820, venue start LATER than ours              820  (100 %)
#     of the 820, venue start EARLIER than ours              0
#     of the 827, venue start still in the FUTURE          566
#
# **Not one of the 25,079 is `scheduled`.** The listing stamp is always in the
# past, so every row minted from it has already sailed past its invented kickoff
# — which is why the band is `suspended`, and why the page renders "No result
# reported" for matches nobody has played. The skew runs +0.33 h to +658 h and is
# CONTINUOUS (10 / 197 / 200 / 180 / 233 across <6h, 6-24h, 1-3d, 3-7d, >7d), so
# there is no cliff separating "real skew" from "wrong stamp" and a magnitude cap
# would be a fiction — worse, it would exclude the 233 rows that are most plainly
# broken, every one of which has a start still in the future. Polymarket simply
# lists some fixtures weeks ahead. The guards below are the measured ones instead.
#
# WHY THE STATUS MOVES WITH THE DATE, IN ONE TRANSACTION. Re-dating alone is
# INERT for the reader: nothing in the state machine demotes `suspended`, so the
# row would carry a correct future start and keep saying "No result reported"
# forever. Worse, writing the status alone would be undone within a beat —
# `espn_sync`'s `scheduled → live` arm selects on `commence_time <= now`, so a row
# set back to `scheduled` while still holding the listing stamp is promoted
# straight back. The two writes are only correct together, which is why they are
# one UPDATE.
#
# THE EVIDENCE THAT SAYS THESE MATCHES HAVE NOT BEEN PLAYED. Of the 566 rows this
# moves to `scheduled`: **0 carry a score, 0 a period, 0 a game clock, 0 a
# `completed_at`.** Not most — the entire population, the same shape and the same
# argument `commence_time_is_a_reported_start` makes one module over about its own
# 705 rows. The predicate below still refuses on any of those four signals, so the
# guard is real rather than decorative the day one of them appears.

#: Candidate rows for the re-date, with their group's venue instant.
#:
#: Module scope and public for the same reason ``LINK_SUB_MARKETS_SQL`` is: a
#: guard can execute it without driving a whole poll.
#:
#: Two group-level gates, both measured rather than assumed:
#:
#: * ``n_stamps = 1`` — a group must agree with itself about when the fixture is.
#:   Measured 2026-09-14: no group carries two distinct ``venue_game_start``
#:   values (max 1 of 895), so this costs nothing today and fails CLOSED if that
#:   ever stops being true, rather than letting ``min()`` pick a winner by
#:   collation.
#: * ``n_events = 1`` — a group must name exactly ONE event. Measured: **21 of
#:   895 groups link to 2 or 3 different events.** A group holds ONE fixture
#:   instant, so on those the same instant would be written onto up to three
#:   different fixtures and at most one could be right. That is a MATCHING defect
#:   (the twins class, #2693 / lane1's), not a dating one, and re-dating it would
#:   paper over it with a confident wrong time. They are excluded and counted.
REDATE_LISTING_STAMPED_SQL = """
    WITH cand AS (
        SELECT DISTINCT fm.group_id
        FROM events e
        JOIN futures_markets fm ON fm.event_id = e.id
        WHERE fm.source = 'polymarket'
          AND fm.group_id IS NOT NULL
          AND e.commence_time_source = :listing_src
          AND e.status IN ('live', 'suspended')
    ),
    grp AS (
        SELECT p.group_id,
               count(DISTINCT p.market_metadata->>'venue_game_start')
                   FILTER (WHERE p.market_metadata->>'venue_game_start' IS NOT NULL)
                   AS n_stamps,
               min(p.market_metadata->>'venue_game_start') AS vgs,
               count(DISTINCT p.event_id) FILTER (WHERE p.event_id IS NOT NULL)
                   AS n_events,
               min(p.event_id) AS only_event_id,
               array_agg(p.name) FILTER (WHERE p.event_id IS NOT NULL)
                   AS linked_names,
               array_agg(coalesce(p.external_id, ''))
                   FILTER (WHERE p.event_id IS NOT NULL) AS linked_external_ids
        FROM futures_markets p
        JOIN cand c ON c.group_id = p.group_id
        WHERE p.source = 'polymarket'
        GROUP BY p.group_id
    )
    SELECT e.id            AS event_id,
           e.home_team_name AS home_team_name,
           e.away_team_name AS away_team_name,
           g.linked_names   AS linked_names,
           g.linked_external_ids AS linked_external_ids,
           e.commence_time AS event_commence,
           e.completed_at  AS completed_at,
           e.home_score    AS home_score,
           e.away_score    AS away_score,
           e.period        AS period,
           e.game_clock    AS game_clock,
           e.status        AS status,
           g.group_id      AS group_id,
           g.vgs           AS venue_game_start,
           g.n_stamps      AS n_stamps,
           g.n_events      AS n_events
    FROM grp g
    JOIN events e ON e.id = g.only_event_id
    WHERE g.n_stamps = 1
      AND g.n_events = 1
      AND e.commence_time_source = :listing_src
      AND e.status IN ('live', 'suspended')
    ORDER BY e.id
"""


#: The value ``commence_time_source`` carries on a row minted from the listing
#: stamp — the population this rail exists to repair, and the value the write
#: below re-asserts before it replaces it.
LISTING_COMMENCE_SOURCE = "polymarket"


#: Every column the decision was made on, re-asserted inside the write itself.
#:
#: CERT-2834'S FINDING, WHICH IS REAL. The first cut selected the band in one
#: statement and then wrote each row by ``WHERE id = :id``. Between those two
#: statements is an open window, and the realtime score poll writes into exactly
#: this band: a score landing inside the window is read by nobody, and the repair
#: — holding values it read seconds ago — commits ``status = 'scheduled'`` over a
#: game that has visibly started. A reader then sees a live match badged as not
#: yet begun. Selecting a row into a repair band is not permission to write over
#: it; the write needs its own guard.
#:
#: So the UPDATE re-states the whole eligibility tuple and matches zero rows if
#: anything moved. Three deliberate choices:
#:
#: * **Every column, not the ones that look decisive.** ``commence_time``,
#:   ``status``, both scores, ``period``, ``game_clock``, ``completed_at`` and
#:   ``commence_time_source`` — the four inputs ``redate_target`` refuses on, plus
#:   the three columns this statement WRITES. Asserting only what the predicate
#:   READ is the trap: a prior repair in this codebase reconciled exactly while a
#:   column it never looked at moved under an otherwise-identical tuple.
#: * **``IS NOT DISTINCT FROM``, not ``=``.** Six of the eight are nullable and
#:   NULL is the common value; ``= NULL`` is never true, so an ``=`` form would
#:   silently match nothing and this rail would repair zero rows while reporting
#:   success.
#: * **Every bind CAST.** ``IS NOT DISTINCT FROM $1`` gives Postgres nothing to
#:   infer a parameter type from, and asyncpg raises rather than guessing. The
#:   casts are the column's own types, so a schema change that renames or retypes
#:   one fails loudly here instead of quietly widening the match.
#:
#: CERT-2837'S FINDING, WHICH IS ALSO REAL, AND IS WHY THE TWO ``EXISTS`` ARE
#: HERE. The first cut re-asserted the group gates only NEGATIVELY: no second
#: event, no disagreeing stamp. Both are satisfied by a group that has no rows
#: left at all. Phase 1.5 detaches a mislinked market by committing
#: ``event_id = NULL``, and when it does so to every market in this group inside
#: the window, both ``NOT EXISTS`` pass VACUOUSLY — nothing to find — and the
#: stale repair retimes and reschedules an event whose Polymarket evidence has
#: just been withdrawn. The withdrawal is precisely the signal that this group
#: never owned this fixture (CERT-2835's class), so writing its instant is the
#: worst available outcome: a confident wrong kickoff, sourced to a provider that
#: has stopped saying it.
#:
#: An absence cannot be asserted with a negative. So the write also states the
#: two things positively — this group still links THIS event, and this group
#: still carries the stamp about to be written. Together with the two negatives
#: they reconstruct exactly the SELECT's own premise (``n_events = 1`` and it is
#: this event; ``n_stamps = 1`` and it is this stamp).
#:
#: They are two clauses and not one deliberately. It is tempting to require a
#: single row carrying BOTH the link and the stamp, which is stronger — and
#: wrong: a Polymarket group is a parent and its children, the child row carries
#: the venue kickoff (the ingest half of #6073) and the link need not sit on that
#: same row. A combined form would decline rows whose evidence is entirely
#: intact, which is the `= NULL` failure of the first cut wearing the other face:
#: a rail that repairs nothing and reports success. The SELECT derives the two
#: facts by separate aggregates over the group; the guard re-asserts them the
#: same way.
#:
#: The two ``NOT EXISTS`` re-assert the GROUP gates for the same reason. Their
#: window is not the score poll but the matcher: `match_prediction_markets` runs
#: every 15 minutes and can link another market into this group, or relink one
#: away, after the select. A group that has gained a second event no longer names
#: one fixture, and a group that has gained a second stamp no longer agrees with
#: itself about when that fixture is — in both cases the instant about to be
#: written may belong to a different match, which is the mislink class (#2693)
#: and not ours to paper over with a confident wrong time.
_REDATE_UNCHANGED_WHERE = """
    WHERE e.id = :id
      AND e.commence_time IS NOT DISTINCT FROM CAST(:was_commence AS timestamptz)
      AND e.commence_time_source IS NOT DISTINCT FROM CAST(:listing_src AS text)
      AND e.status IS NOT DISTINCT FROM CAST(:was_status AS text)
      AND e.home_score IS NOT DISTINCT FROM CAST(:was_home_score AS integer)
      AND e.away_score IS NOT DISTINCT FROM CAST(:was_away_score AS integer)
      AND e.period IS NOT DISTINCT FROM CAST(:was_period AS text)
      AND e.game_clock IS NOT DISTINCT FROM CAST(:was_game_clock AS text)
      AND e.completed_at IS NOT DISTINCT FROM CAST(:was_completed_at AS timestamptz)
      AND EXISTS (
          SELECT 1 FROM futures_markets fm1
          WHERE fm1.group_id = CAST(:group_id AS text)
            AND fm1.source = 'polymarket'
            AND fm1.event_id = :id
      )
      AND EXISTS (
          SELECT 1 FROM futures_markets fm1s
          WHERE fm1s.group_id = CAST(:group_id AS text)
            AND fm1s.source = 'polymarket'
            AND fm1s.market_metadata->>'venue_game_start'
                IS NOT DISTINCT FROM CAST(:was_venue_game_start AS text)
      )
      AND NOT EXISTS (
          SELECT 1 FROM futures_markets fm2
          WHERE fm2.group_id = CAST(:group_id AS text)
            AND fm2.source = 'polymarket'
            AND fm2.event_id IS NOT NULL
            AND fm2.event_id <> :id
      )
      AND NOT EXISTS (
          SELECT 1 FROM futures_markets fm3
          WHERE fm3.group_id = CAST(:group_id AS text)
            AND fm3.source = 'polymarket'
            AND fm3.market_metadata->>'venue_game_start' IS NOT NULL
            AND fm3.market_metadata->>'venue_game_start'
                <> CAST(:was_venue_game_start AS text)
      )
"""

#: The corrected start, when the row's state is not ours to judge.
REDATE_WRITE_DATE_ONLY_SQL = f"""
    UPDATE events AS e
    SET commence_time = :dt,
        commence_time_source = :src
    {_REDATE_UNCHANGED_WHERE}
"""

#: The corrected start AND the status, in ONE statement, never two: a status
#: written without the date is promoted straight back to `live` within a beat by
#: `espn_sync`'s `commence_time <= now` arm.
REDATE_WRITE_WITH_STATUS_SQL = f"""
    UPDATE events AS e
    SET commence_time = :dt,
        commence_time_source = :src,
        status = :status
    {_REDATE_UNCHANGED_WHERE}
"""


#: The rows whose own two columns contradict each other: a venue-dated fixture
#: standing `live` or `suspended` over a kickoff that has not happened yet.
#:
#: WHY THIS BAND EXISTS SEPARATELY FROM THE ONE ABOVE, which is the whole point.
#: The sweep above repairs `commence_time_source = 'polymarket'` and its write
#: sets that column to `polymarket_venue` — so **every row it repairs leaves its
#: population permanently**, and it can never re-select one. Phase 1.5 in the
#: registry (#6073's other half, lane1's) writes the same corrected date onto
#: already-linked rows the group-keyed sweep above structurally cannot reach —
#: measured 2026-09-14: **47 events in 26 multi-event groups**, excluded by the
#: sweep's `n_events = 1` gate because a group-level aggregate cannot tell a twin
#: from a different fixture. Of those 47, **12 have a venue start still in the
#: future**. Phase 1.5 writes the DATE and not the STATUS, and
#: `transition_event_statuses` has no `suspended → scheduled` edge (its four are
#: scheduled→live, live→suspended, suspended→live, suspended→retired). So the
#: moment `bainluck-heavy` carries that writer, ~12 rows enter a state **no
#: deployed rail can drain**: an honest date reading "No result reported".
#:
#: This band is keyed on neither rail, which is what makes it order-independent.
#: It asks the row a question the row alone can answer — *you say you are live or
#: stale, and you say you start next week; which is it?* — so it drains the class
#: whichever writer produced it, in either execution order, and keeps draining it
#: if a third writer appears. `poll_polymarket_markets` is NOT in `HEAVY_TASKS`,
#: so this ships with the ordinary web release and is live BEFORE the attended
#: heavy deploy that arms the writer producing the population.
#:
#: Scoped to `polymarket_venue` ON PURPOSE, and the other branch was counted
#: before the scope was chosen. The self-contradiction is decidable for any
#: source, and the whole class is **0 rows across every source** today (measured
#: 2026-09-14 11:52Z). Widening to all sources would adopt other providers'
#: status semantics — a postponed ESPN fixture carrying a future rescheduled date
#: may mean `suspended` honestly — on a population this lane has never measured
#: over time. `polymarket_venue` is the one value that means "we positively
#: established this kickoff from the venue's own listing", so it is the one date
#: a status may be asserted against. Rows still stamped `polymarket` carry the
#: listing stamp this ship exists to distrust and are deliberately left to the
#: sweep above, which fixes their date and status in ONE statement.
STUCK_FUTURE_STATUS_SQL = """
    SELECT e.id            AS event_id,
           e.commence_time AS event_commence,
           e.completed_at  AS completed_at,
           e.home_score    AS home_score,
           e.away_score    AS away_score,
           e.period        AS period,
           e.game_clock    AS game_clock,
           e.status        AS status
    FROM events e
    WHERE e.commence_time_source = :venue_src
      AND e.status IN ('live', 'suspended')
      AND e.commence_time > now()
      AND e.completed_at IS NULL
      AND e.home_score IS NULL
      AND e.away_score IS NULL
      AND e.period IS NULL
      AND e.game_clock IS NULL
    ORDER BY e.id
"""


#: The same compare-and-write discipline CERT-2834 required of the sweep above,
#: for the same reason: selecting a row into a repair band is not permission to
#: write over it. The realtime score poll writes into exactly this band, and a
#: score landing between the select and the write means the game HAS started —
#: at which point `scheduled` is the lie, not `live`.
#:
#: Every column the decision read is re-asserted, and `IS NOT DISTINCT FROM`
#: rather than `=` because six of the seven are nullable and NULL is their common
#: value — an `=` form would match nothing and the rail would repair zero rows
#: while reporting success.
#:
#: The casts are belt-and-braces here, and that is a MEASUREMENT rather than the
#: sibling's inherited claim. `_REDATE_UNCHANGED_WHERE` above says every bind must
#: be CAST because `IS NOT DISTINCT FROM $1` leaves asyncpg no parameter type to
#: infer; true there, where binds meet `jsonb->>` expressions. Measured against a
#: real server 2026-09-14, removing all eight casts from THIS statement changes
#: nothing — every bind sits opposite a typed column and Postgres infers it. They
#: stay for symmetry and cost nothing, but nobody should believe they are what
#: keeps this rail alive. `commence_time` and
#: `commence_time_source` are both here even though this statement writes
#: neither: they are the premise ("a venue-established kickoff, in the future"),
#: and a repair that reconciles exactly while a column it never looked at moves
#: underneath is a failure this codebase has already had once.
#: CERT-2858'S FOLLOW-UP, AND WHY IT IS SPELLED `clock_timestamp()`. The review
#: asked for `e.commence_time > now()` here: the tuple guard below preserves the
#: SELECTED kickoff, but nothing re-evaluated that the kickoff is STILL in the
#: future if wall time crossed it between the select and the write. Real, and
#: worth closing — a long lock wait, or simply a large band, and the rail commits
#: `scheduled` onto a match that started while it worked.
#:
#: But `now()` is `transaction_timestamp()`, and this pass runs its SELECT and
#: every one of its UPDATEs inside ONE transaction. Measured on a real server
#: 2026-09-14, in one transaction across a 1-second sleep: `now()` returned
#: `05:18:00.183978` before AND after, while `clock_timestamp()` moved
#: `05:18:00.191642` → `05:18:01.204789`. So the recommended form compares the
#: kickoff against the same instant the band already compared it against, can
#: never decline anything, and would sit here reading exactly like a guard.
#: `clock_timestamp()` is statement-time and is the one that fires.
_STUCK_STATUS_UNCHANGED_WHERE = """
    WHERE e.id = :id
      AND e.commence_time > clock_timestamp()
      AND e.commence_time IS NOT DISTINCT FROM CAST(:was_commence AS timestamptz)
      AND e.commence_time_source IS NOT DISTINCT FROM CAST(:venue_src AS text)
      AND e.status IS NOT DISTINCT FROM CAST(:was_status AS text)
      AND e.home_score IS NOT DISTINCT FROM CAST(:was_home_score AS integer)
      AND e.away_score IS NOT DISTINCT FROM CAST(:was_away_score AS integer)
      AND e.period IS NOT DISTINCT FROM CAST(:was_period AS text)
      AND e.game_clock IS NOT DISTINCT FROM CAST(:was_game_clock AS text)
      AND e.completed_at IS NOT DISTINCT FROM CAST(:was_completed_at AS timestamptz)
"""

#: The status alone. The date is correct by this band's own premise — that is
#: what `commence_time > now()` on a `polymarket_venue` row MEANS — so there is
#: nothing to move, and moving it would overwrite the venue's own statement.
#:
#: This is not the hazard `REDATE_WRITE_WITH_STATUS_SQL` warns about, and the
#: difference is worth stating because the two comments look contradictory. There,
#: a status written without the date leaves a start in the PAST, and
#: `espn_sync`'s `commence_time <= now` arm promotes the row straight back to
#: `live` within a beat. Here the start is in the FUTURE, so that arm does not
#: fire until the real hour — which is precisely the behaviour wanted.
STUCK_STATUS_WRITE_SQL = f"""
    UPDATE events AS e
    SET status = :status
    {_STUCK_STATUS_UNCHANGED_WHERE}
"""


#: Separators that mean "token boundary" inside a competitor's name.
_IDENTITY_SEPARATORS = re.compile(r"[-_/]+")
#: Everything else non-word is noise and is DELETED, not spaced — see
#: `_same_participant` for why "F.C." must fold to `fc` and never to `f c`.
_IDENTITY_PUNCTUATION = re.compile(r"[^\w\s]")


def _identity_tokens(name: str) -> set:
    """The name's identity-bearing tokens — built from primitives, on purpose.

    CERT-2845 AND CERT-2847, WHICH ARE ONE DEFECT WITH TWO SPELLINGS. This fold
    reached for a shared normalizer twice and was wrong twice.
    `normalize_team_name_for_matching` strips the bare suffixes (`b`, `ii`,
    `u21`, `women`), so "FC Barcelona B" was the senior side.
    `normalize_team_name` keeps those and strips trailing PARENTHETICALS, so
    "FC Barcelona (B)" was the senior side. Each fix closed the spelling in front
    of it and left the class open.

    The cause is not which normalizer: it is that BOTH are built for a matcher
    trying to find a home for a market, where discarding a qualifier widens the
    net helpfully. This rail asks the opposite question — is this the SAME
    competitor — and for that every discarded token is evidence thrown away
    before the comparison. Borrowing a normalizer means inheriting its opinion
    about what does not matter, and that opinion is the bug.

    So the fold is assembled here from primitives that only ever fold FORM, never
    drop content: diacritics and case (`strip_diacritics` + `lower`), separators
    to token boundaries, and remaining punctuation deleted rather than spaced.
    Nothing is stripped, so no qualifier can be silently discarded and no future
    edit to a shared normalizer can reopen this from a third direction.

    It also makes the two spellings agree with each other, which is right:
    "FC Barcelona (B)" and "FC Barcelona B" are `{fc, barcelona, b}` both ways,
    so a market may write either and still date its own fixture, while neither
    can date the senior one.

    Measured: 204/204 reach on the live band, and correct on all 18 adversarial
    titles this ship has accumulated.
    """
    folded = strip_diacritics(name or "").lower()
    folded = _IDENTITY_SEPARATORS.sub(" ", folded)
    folded = _IDENTITY_PUNCTUATION.sub("", folded)
    return set(folded.split())


def _same_participant(market_name: str, event_name: str) -> bool:
    """One competitor, named twice — or two competitors who share a surname?

    CERT-2843. The house `names_match` answers a DIFFERENT question well: it
    ranks candidates for a matcher that is trying to find a home for a market,
    and for that a 0.5 token overlap is a reasonable third stage. Used as an
    identity test it says "Alexander Zverev" IS "Mischa Zverev", because the
    surname is half the tokens. The fixtures most at risk of being confused are
    precisely the ones this rail must not confuse: the Zverev brothers, the
    Tsitsipas brothers, the Williams sisters.

    So: equal token SETS after the house normalization (which strips diacritics,
    case and punctuation, so "Zvereva" vs "Zvereva." and accented spellings are
    not the failure this is about). A set rather than a sequence because "Last,
    First" and "First Last" are the same person and a market may write either;
    every token still has to be accounted for on both sides, which is the part
    that makes it an identity test rather than a similarity score.

    Deliberately NOT accepting a subset. "Zverev" alone is a legitimate subset of
    "Alexander Zverev" and identifies neither brother, so allowing subsets would
    reopen the hole this closes from the other end. Measured: 204/204 reach on
    the live band either way, so nothing is bought by the looser rule.

    Squad, youth and women's qualifiers are part of the identity — a B team is
    not its first team, and the two play on different days. Keeping them is the
    whole point of `_identity_tokens` building its own fold instead of borrowing
    a matcher's normalizer; CERT-2845 and CERT-2847 are both that mistake.
    """
    market_tokens = _identity_tokens(market_name)
    event_tokens = _identity_tokens(event_name)
    return bool(market_tokens) and market_tokens == event_tokens


def group_names_this_fixture(
    *,
    linked_names,
    linked_external_ids,
    home_team_name,
    away_team_name,
) -> bool:
    """Does the group's own evidence NAME the fixture it is about to re-date?

    CERT-2840'S FINDING. Every gate before this one is about COUNTING: one event
    in the group, one stamp, nothing moved underneath. A group can satisfy all of
    them and still be wrong about which match it describes — a single market
    mislinked to a single event has `n_events = 1` and `n_stamps = 1`, so the
    sweep took a Serena-Gauff market's kickoff and wrote it onto a
    Mazzola-Zeltina fixture. That is the mislink class (#2693) and it is worse
    here than elsewhere, because the instant lands with
    `commence_time_source = 'polymarket_venue'` attached: a confident wrong
    kickoff, sourced.

    A provenance string says WHERE a value came from. It never proves the value
    is about the row it is written to. Nothing upstream of this rail establishes
    that, so the rail has to establish it itself.

    The check parses the market title (with the matcher's ticker fallback) and
    requires BOTH of the parsed participants to map onto this event's two teams,
    one-to-one, in either orientation. The rail does not care which side is home,
    only that the market is talking about this match.

    BOTH SIDES, AND THAT IS CERT-2842. The obvious move is the matcher's own
    `match_teams_to_event`, and it is the wrong tool here: it returns an
    orientation as soon as ONE side matches, which is the right answer to the
    question the matcher asks it — *which way round is this market* — and the
    wrong answer to the question this rail asks it. A market reading
    "Mazzola vs. Serena" shares a participant with "Mazzola vs. Zeltina" and is a
    different match; one-sided agreement accepted it and re-dated the fixture. On
    a tour a single player appears in a great many fixtures, so one matched name
    is close to no evidence at all.

    AND EVERY TOKEN, WHICH IS CERT-2843. The next reach for the comparison is
    the house `names_match`, and it is also the wrong tool here: its third stage
    accepts a token overlap of 0.5, so "Alexander Zverev" and "Mischa Zverev"
    are the same person to it, on the surname alone. That is a sensible rule for
    a matcher trying to find a home for a market and a dangerous one for a rail
    writing a kickoff: tennis has the Zverev brothers, the Tsitsipas brothers and
    the Williams sisters, and a sibling pair is exactly the fixture most likely
    to be confused with its sibling pair.

    So participants are compared by `_same_participant`, below: equal NAME TOKEN
    SETS after the house normalization. Every token has to be accounted for in
    both directions, which is what stops a shared surname standing in for a
    shared person.

    ANY of the group's linked markets satisfying it is enough. A Polymarket group
    is a parent and its children and they carry different titles; requiring all
    of them to parse would decline legitimate groups over a child whose name is a
    prop. Requiring none is what shipped and is the defect.

    MEASURED BEFORE ADOPTING, because a validator that cannot read our own titles
    would silently reduce this rail to repairing nothing while reporting success
    — the failure this ship has now twice had to design around. Over both ends of
    the live band on 2026-09-14 (two 500-row slices, head and tail, 204 distinct
    events across soccer, tennis, rugby, esports, cricket and ice hockey):
    204/204 under the one-sided form, and 204/204 again under the two-sided form
    shipped here. The stricter rule costs no reach.
    """
    names = list(linked_names or [])
    ext_ids = list(linked_external_ids or [])
    if not names or not (home_team_name and away_team_name):
        # No linked market left to speak for the group, or an event with no teams
        # to compare against. Either way the pairing is unproven, and unproven is
        # the one thing this rail must not write on.
        return False
    for i, name in enumerate(names):
        external_id = ext_ids[i] if i < len(ext_ids) else ""
        matchup = extract_matchup_with_ticker_fallback(name or "", external_id or "")
        if matchup is None:
            continue
        market_a = (matchup.team_a or "").strip()
        market_b = (matchup.team_b or "").strip()
        if not (market_a and market_b):
            # A title naming one participant — a tournament-winner or an
            # outright — is a valid market and no evidence about when one
            # fixture starts.
            continue
        straight = _same_participant(market_a, home_team_name) and _same_participant(
            market_b, away_team_name
        )
        swapped = _same_participant(market_a, away_team_name) and _same_participant(
            market_b, home_team_name
        )
        if straight or swapped:
            return True
    return False


def redate_target(
    *,
    venue_game_start,
    event_commence,
    now,
    completed_at=None,
    home_score=None,
    away_score=None,
    period=None,
    game_clock=None,
) -> Optional[tuple]:
    """What should this row's ``(commence_time, status_or_None)`` become?

    ``None`` ⇒ leave the row alone. A tuple's second element is ``None`` when the
    date moves but the status is not ours to judge.

    Pure, so every refusal below is provable without a database. The refusals,
    each one measured against the production band in the block above:

    * **No venue instant, or one that will not parse.** Nothing to write.
    * **The move must be FORWARD.** Measured 820/820 later, 0 earlier — so this
      costs nothing today and closes the one hazard that would matter if a later
      poll ever published an earlier instant: moving a start BACKWARD can only
      make a match that has not happened read as one that has, which is the exact
      defect #6073 is about. A tie (the instants already agree) is also nothing to
      do, and returns ``None`` rather than a no-op write.
    * **Any evidence of play refuses the whole row.** A score — even ``0`` — a
      period, or a running clock all mean something reported on this game, and a
      row something reported on is not a row we may silently re-date and un-start.
      Measured: 0 of 566 carry any of the four, so this refuses nothing today and
      is the guard that holds the day one appears.
    * **Never past ``completed_at`` (gotcha #46).** ``completed_at >=
      commence_time`` is an invariant whose violation means a cross-event data
      merge, so a target that would invert it is refused rather than clamped.
      Measured: 0 of 827 carry ``completed_at`` at all.

    THE STATUS, AND WHY ONLY ONE DIRECTION OF IT. When the corrected start is
    still in the FUTURE the row's state is positively wrong — it cannot be
    `suspended`, because a match that has not begun has not gone stale — and the
    honest state is ``scheduled``; the ordinary promotion gate then takes it live
    at the real hour, because ``polymarket_venue`` is a reported start and passes
    ``commence_time_is_a_reported_start``. When the corrected start is in the PAST
    the date was still wrong and is still worth fixing, but whether the row is
    live, finished or stale is not something this rail can know — so it writes the
    date and leaves ``status`` alone, exactly as ``_refine_stand_in_event_starts``
    does one provider over.
    """
    if venue_game_start is None:
        return None
    if isinstance(venue_game_start, str):
        try:
            target = datetime.fromisoformat(venue_game_start.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        target = venue_game_start
    if target is None or event_commence is None:
        return None
    target = target if target.tzinfo else target.replace(tzinfo=timezone.utc)
    current = (
        event_commence
        if event_commence.tzinfo
        else event_commence.replace(tzinfo=timezone.utc)
    )
    if target <= current:
        return None
    if (
        home_score is not None
        or away_score is not None
        or period is not None
        or game_clock is not None
    ):
        return None
    if completed_at is not None:
        completed = (
            completed_at
            if completed_at.tzinfo
            else completed_at.replace(tzinfo=timezone.utc)
        )
        if target > completed:
            return None
    reference = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return (target, "scheduled" if target > reference else None)


async def redate_polymarket_listing_stamped_events() -> dict:
    """Give every already-minted Polymarket fixture the venue's own start.

    #6073, the third half. See the block above for the population, the measured
    guards and why the status rides with the date.

    Returns a stats dict — ``moved``, ``rescheduled``, ``skipped_*`` — so a poll
    that repairs nothing says so out loud rather than reading as a success
    (``app/utils/task_verdict.py``: "it returned" is not "it worked").
    """
    stats = {
        "scanned": 0,
        "moved": 0,
        "rescheduled": 0,
        "skipped_multi_event_group": 0,
        "skipped_ambiguous_stamp": 0,
        "skipped_unpaired_group": 0,
        "skipped_no_change": 0,
        "skipped_raced": 0,
    }
    async with get_task_session() as session:
        result = await session.execute(
            text(REDATE_LISTING_STAMPED_SQL),
            {"listing_src": LISTING_COMMENCE_SOURCE},
        )
        rows = result.fetchall()
        now = datetime.now(timezone.utc)

        for r in rows:
            stats["scanned"] += 1
            # Both gates are in the SQL's WHERE as well; re-asserted here so the
            # refusal is provable in a unit test and so a future edit to either
            # place cannot quietly drop one of them.
            if r.n_events != 1:
                stats["skipped_multi_event_group"] += 1
                continue
            if r.n_stamps != 1:
                stats["skipped_ambiguous_stamp"] += 1
                continue
            # CERT-2840. Counting the group's rows says nothing about WHICH match
            # they describe: one market mislinked to one event passes every gate
            # above. Before this rail attributes an instant to a provider, the
            # provider's own title has to name this fixture.
            if not group_names_this_fixture(
                linked_names=r.linked_names,
                linked_external_ids=r.linked_external_ids,
                home_team_name=r.home_team_name,
                away_team_name=r.away_team_name,
            ):
                stats["skipped_unpaired_group"] += 1
                logger.warning(
                    "redate: group %s does not name event %s (%s vs %s) — "
                    "not re-dating on a link this rail cannot verify",
                    r.group_id,
                    r.event_id,
                    r.home_team_name,
                    r.away_team_name,
                )
                continue
            decision = redate_target(
                venue_game_start=r.venue_game_start,
                event_commence=r.event_commence,
                now=now,
                completed_at=r.completed_at,
                home_score=r.home_score,
                away_score=r.away_score,
                period=r.period,
                game_clock=r.game_clock,
            )
            if decision is None:
                stats["skipped_no_change"] += 1
                continue
            target, new_status = decision
            # Every column the decision was made on travels back into the
            # write's own WHERE — see `_REDATE_UNCHANGED_WHERE`. A row that moved
            # between the select and here simply does not match.
            params = {
                "dt": target,
                "src": POLYMARKET_VENUE_COMMENCE_SOURCE,
                "id": r.event_id,
                "listing_src": LISTING_COMMENCE_SOURCE,
                "was_commence": r.event_commence,
                "was_status": r.status,
                "was_home_score": r.home_score,
                "was_away_score": r.away_score,
                "was_period": r.period,
                "was_game_clock": r.game_clock,
                "was_completed_at": r.completed_at,
                "group_id": r.group_id,
                "was_venue_game_start": r.venue_game_start,
            }
            if new_status is None:
                sql = REDATE_WRITE_DATE_ONLY_SQL
            else:
                sql = REDATE_WRITE_WITH_STATUS_SQL
                params["status"] = new_status
            written = await session.execute(text(sql), params)
            if (written.rowcount or 0) == 0:
                # The row moved under us. Counted and named, never silent: a
                # repair that writes nothing must not read as one that worked
                # (`app/utils/task_verdict.py`).
                stats["skipped_raced"] += 1
                logger.info(
                    "Polymarket re-date (#6073): event %s changed between "
                    "selection and write — left alone",
                    r.event_id,
                )
                continue
            stats["moved"] += 1
            if new_status is not None:
                stats["rescheduled"] += 1

        if stats["moved"]:
            await session.commit()
        logger.info(
            "Polymarket re-date (#6073): scanned %d, moved %d (%d back to "
            "scheduled), skipped %d multi-event group / %d ambiguous stamp / "
            "%d no change / %d raced",
            stats["scanned"], stats["moved"], stats["rescheduled"],
            stats["skipped_multi_event_group"], stats["skipped_ambiguous_stamp"],
            stats["skipped_no_change"], stats["skipped_raced"],
        )
        return stats


def stuck_status_target(
    *,
    status,
    event_commence,
    now,
    completed_at=None,
    home_score=None,
    away_score=None,
    period=None,
    game_clock=None,
) -> Optional[str]:
    """Is this row's status refuted by its own kickoff, and what should it be?

    ``None`` ⇒ leave the row alone. Pure, so every refusal is provable without a
    database — and deliberately built from the SAME four refusals as
    ``redate_target`` so the two rails cannot drift into disagreeing about what
    "nothing has been reported on this game" means.

    The refusals:

    * **Only ``live`` and ``suspended`` are refutable.** Those two both assert the
      match has begun. ``scheduled`` already agrees with a future start; a
      settled/closed/retired row is a state this rail has no standing to reopen.
    * **The start must be in the FUTURE.** This is the entire evidence. A start in
      the past makes ``live`` or ``suspended`` perfectly honest, and a rail that
      rewrote those would un-start real games — the mirror image of the defect
      #6073 is about.
    * **Any evidence of play refuses the row.** A score — even ``0`` — a period or
      a running clock all mean something was reported on this game, and a row
      something was reported on is not one we may badge as not yet begun. This is
      the guard that matters most here: it is what stands between this rail and
      the race the compare-and-write also covers, and it is asserted in the band,
      in this function, and in the write's own ``WHERE``.
    * **``completed_at`` refuses the row.** A finished match dated into the future
      is a violated invariant (gotcha #46) and a cross-event merge symptom — a
      MATCHING defect to be reported, never something to tidy away by re-badging
      the row as upcoming.

    Nothing here reads a provider, a market, a group or a stamp. That is the
    design: the contradiction is decidable from the row alone, so the repair is
    independent of which writer produced it and of the order the writers ran in.
    """
    if status not in ("live", "suspended"):
        return None
    if event_commence is None:
        return None
    if (
        home_score is not None
        or away_score is not None
        or period is not None
        or game_clock is not None
    ):
        return None
    if completed_at is not None:
        return None
    start = (
        event_commence
        if event_commence.tzinfo
        else event_commence.replace(tzinfo=timezone.utc)
    )
    reference = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if start <= reference:
        return None
    return "scheduled"


async def rescue_stuck_future_status_events() -> dict:
    """Un-stick venue-dated fixtures badged live/stale over a future kickoff.

    #6073's last gap. See ``STUCK_FUTURE_STATUS_SQL`` for the population, why it
    is keyed on the row rather than on either writer, and the measured 12 rows
    that enter it when `bainluck-heavy` carries the registry's Phase 1.5.

    Returns a stats dict so a sweep that repairs nothing says so out loud rather
    than reading as a success (``app/utils/task_verdict.py``). **A zero here is
    the expected reading today** — the class is measured empty until the heavy
    deploy lands — and that is exactly why it is counted rather than logged only
    when non-zero: the number going from 0 to 12 and back to 0 is the evidence
    this rail works.
    """
    stats = {
        "scanned": 0,
        "rescheduled": 0,
        "skipped_not_refuted": 0,
        "skipped_raced": 0,
    }
    async with get_task_session() as session:
        result = await session.execute(
            text(STUCK_FUTURE_STATUS_SQL),
            {"venue_src": POLYMARKET_VENUE_COMMENCE_SOURCE},
        )
        rows = result.fetchall()
        now = datetime.now(timezone.utc)

        for r in rows:
            stats["scanned"] += 1
            # Re-asserted here as well as in the band so every refusal is
            # provable in a unit test, and so an edit to either place cannot
            # quietly drop one of them.
            new_status = stuck_status_target(
                status=r.status,
                event_commence=r.event_commence,
                now=now,
                completed_at=r.completed_at,
                home_score=r.home_score,
                away_score=r.away_score,
                period=r.period,
                game_clock=r.game_clock,
            )
            if new_status is None:
                stats["skipped_not_refuted"] += 1
                continue
            written = await session.execute(
                text(STUCK_STATUS_WRITE_SQL),
                {
                    "status": new_status,
                    "id": r.event_id,
                    "venue_src": POLYMARKET_VENUE_COMMENCE_SOURCE,
                    "was_commence": r.event_commence,
                    "was_status": r.status,
                    "was_home_score": r.home_score,
                    "was_away_score": r.away_score,
                    "was_period": r.period,
                    "was_game_clock": r.game_clock,
                    "was_completed_at": r.completed_at,
                },
            )
            if (written.rowcount or 0) == 0:
                # The row moved under us — most likely a score landed, which
                # means the game really has started and `scheduled` would have
                # been the lie. Counted and named, never silent.
                stats["skipped_raced"] += 1
                logger.info(
                    "Stuck-status rescue (#6073): event %s changed between "
                    "selection and write — left alone",
                    r.event_id,
                )
                continue
            stats["rescheduled"] += 1

        if stats["rescheduled"]:
            await session.commit()
        logger.info(
            "Stuck-status rescue (#6073): scanned %d, rescheduled %d, "
            "skipped %d not refuted / %d raced",
            stats["scanned"], stats["rescheduled"],
            stats["skipped_not_refuted"], stats["skipped_raced"],
        )
        return stats


def submarket_is_open(event, market) -> bool:
    """Whether a decomposed sub-market row may be stamped `status='open'`. Pure.

    #6734. The sub-market rows written below are keyed on
    `external_id=market.condition_id` — each one IS an individual Polymarket
    market — but their status has always been read off `event.active`, the
    PARENT's flag. A market the venue has closed while its event still trades
    therefore keeps `status='open'` forever, and the price frozen at the moment
    the book went away keeps being served as a live quote. The filed specimen is
    a LIVE tennis page printing `Over 21.5 / 22.5 / 23.5` all at 51% off three
    different condition ids whose books Gamma answers
    `No orderbook exists for the requested token id`.

    Two independent ways the parent's flag is the wrong question, both reachable
    from this one writer:

      * the market closes under an open event — the specimen above; and
      * the EVENT is closed but Gamma keeps `active=true` on it, which is why
        :func:`sunk_event_is_open` exists. `_process_event_batch` is fed by a
        `closed=True` sweep as well as the open poll, so that population arrives
        here too and is stamped `open` on the same expression.

    Read through `getattr` for the reason the `closed` test in
    `_is_reserved_slot` is: a duck-typed caller carrying no such field keeps
    exactly the old behaviour rather than silently gaining the carve-out.

    STRICTLY TIGHTENING, deliberately. This adds two ways to be `resolved` and
    removes none — it can never turn a stored `resolved` back into `open`. That
    is not incidental: `status` gates `/api/futures/{categories,faceted,
    grouped-feed,movers}`, so a predicate that un-resolved rows would PUSH
    markets onto the feed and into Biggest Movers, and the inverse defect
    (rows stamped `resolved` while the venue still trades them) is a different
    fix with its own blast radius. It is measured and filed, not smuggled in
    here.
    """
    return bool(
        getattr(event, "active", False)
        and not getattr(event, "closed", False)
        and not getattr(market, "closed", False)
    )


def submarket_resolution_date(event, market):
    """The date a decomposed leg resolves on: its own ``endDate``, else its event's. Pure.

    #8466. Every leg used to be stamped with ``event.end_date`` on the belief
    that "decomposed sub-markets carry no per-market date". Gamma carries one
    on every leg, and on a date ladder it is the question itself: event
    1038648's "US x Iran ceasefire continues through September 30?" ends
    09-30 while its event ends 10-31, so Discover printed "Resolves Oct 31,
    2026" on a question settling a month earlier, and the Nov 30 / Dec 31
    legs were stored as resolving BEFORE they do. A game's legs carry the
    event's own date (Cubs-Red Sox 1058697: identical), so games do not move.
    """
    own = getattr(market, "end_date", None) if market is not None else None
    if own is not None:
        return own
    return getattr(event, "end_date", None)


def opening_capture_is_hindsight(event, market, resolution_date, now) -> bool:
    """Whether an opening stamped now would be a hindsight price (#2027).

    Pure. The writer stamping ``opening_probability`` must be able to say
    which of two facts it asserts — "first quote for a live market" or
    "what the book looked like after it settled" (ruling 075, second
    clause). It has both signals in hand and asked neither: the venue's
    own ``closed`` flags, and the capture time against ``resolution_date``
    (ruling 103's predicate, ``opening_captured_at > resolution_date``).

    ``market`` is the sub-market DTO the leg was priced from. CERT-3202: it
    used to be None on the two parent-field writers, which made the refusal
    event-wide — and a Polymarket event stays open while its children settle
    one by one, so a closed child under an open parent (the sole-child case
    included) banked its settled book as the opening. ``_parent_outcome_data``
    now carries the sub-market on each leg, so all four writers ask the same
    question about the same object and a mixed field refuses only its settled
    legs. Passing None is still accepted and still means "no per-child signal",
    but no caller in this module does.

    Naive stamps are read as UTC; an unparseable stamp refuses nothing, so a
    bad clock cannot blank live openings.

    Datetime/date handling is exact, never truncated: an aware datetime
    compares at its full timestamp (``datetime`` is checked BEFORE
    ``date`` because ``datetime`` subclasses ``date`` — the reverse order
    truncates ``2026-09-20T20:00Z`` to midnight and wrongly refuses a live
    market captured at noon). A pure ``date`` compares at UTC midnight.

    Provenance: at the sub-market site ``resolution_date`` is the leg's own
    date (``submarket_resolution_date``, #8466); at the parent-field sites it
    is the parent row's, which is ``event.end_date``.
    """
    if getattr(event, "closed", False) or getattr(event, "archived", False):
        return True
    if market is not None and getattr(market, "closed", False):
        return True
    if resolution_date is not None and now is not None:
        try:
            res = resolution_date
            if isinstance(res, datetime):
                if res.tzinfo is None:
                    res = res.replace(tzinfo=timezone.utc)
            elif isinstance(res, date):
                res = datetime(res.year, res.month, res.day, tzinfo=timezone.utc)
            else:
                return False
            cmp_now = now
            if isinstance(cmp_now, datetime) and cmp_now.tzinfo is None:
                cmp_now = cmp_now.replace(tzinfo=timezone.utc)
            if cmp_now > res:
                return True
        except Exception:
            return False
    return False


async def _process_event_batch(
    events, stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
    pg_insert, probability_to_american, compute_market_tier,
):
    """Process and commit a batch of Polymarket events."""
    from app.utils.futures_categorization import (
        detect_league, detect_season,
        compute_canonical_market_key,
        detect_market_type,
        extract_olympic_discipline,
        generate_category_tags,
    )
    from app.utils.editorial_patterns import matches_editorial_recall as _matches_editorial_recall
    from app.utils.market_label_normalization import game_prop_category

    async with get_task_session() as session:
        now = datetime.now(timezone.utc)

        for event in events:
            try:
                if not event.markets:
                    continue

                # Determine category from tags
                category, llm_sport_category = _tags_to_category(event.tags)

                # Skip crypto markets entirely — they consume DB space
                # without providing value to users
                if llm_sport_category == "crypto" or category == "crypto":
                    stats["crypto_skipped"] += 1
                    continue

                _group_names = [event.title or ""] + [
                    (m.question or "") for m in event.markets
                ]
                category, llm_sport_category, _arm = resolve_event_category(
                    category, llm_sport_category, event.title, _group_names
                )
                # The FALLBACK arm only. That is what this counter has always meant
                # — it lived inside the tagless branch before the extraction — and
                # widening an ops metric is not this queue's to do.
                if _arm == "fallback":
                    stats["by_category"][llm_sport_category or "unknown"] = (
                        stats["by_category"].get(llm_sport_category or "unknown", 0) + 1
                    )

                # #5516 — THE CASCADE ABOVE NEVER READS THE MARKET'S OWN NAME.
                #
                # `resolve_event_category` answers from the EVENT's Polymarket
                # tags, and every arm of it that lands on a sport returns the
                # single value `championship` — that column is really "this is
                # sport", spelled with the wrong word. So "Miami Marlins vs. San
                # Diego Padres - 4th Inning Winner" is stored `championship` and
                # the search card prints **Championship** in the same purple pill
                # as "MLB World Series Champion 2026".
                #
                # #6471 fixed `market_tier` for exactly this population and could
                # not reach the reader, because `components/FuturesCard.tsx`'s chip
                # is `marketCategoryLabel(market.category)` and names neither
                # `market_tier` nor `market_type_label`. `category` is the column a
                # reader actually sees, and it is the one left saying it.
                #
                # THE PREDICATE IS NOT A NEW ONE. `game_prop_category` IS the
                # condition `compute_market_tier` evaluates one line below before
                # it returns 5, so the two columns are one sentence asked twice
                # rather than two classifiers that can disagree — which is the
                # whole defect, not an incidental tidiness.
                #
                # THE DECOMPOSED-CHILD WRITER ALREADY HARDCODES THIS ANSWER
                # (`category="game_prop"`, the sub-market insert below), which is
                # why 86 structurally identical esports "- Map 2 Winner" rows badge
                # "Game Props" today while their baseball twins badge Championship:
                # the two doors disagreed, not the data. Kalshi's door agrees too —
                # all 1,025 open Kalshi rows matching this predicate are already
                # `game_prop`, none `championship` (production, 2026-09-19).
                _game_prop_category = game_prop_category(
                    event.title, category, sport_category=llm_sport_category,
                )
                _category_corrected = bool(
                    _game_prop_category and category != _game_prop_category
                )
                if _category_corrected:
                    category = _game_prop_category
                    stats["category_game_prop_corrected"] = (
                        stats.get("category_game_prop_corrected", 0) + 1
                    )

                # Compute market tier
                market_tier = compute_market_tier(
                    event.title, category,
                    sport_category=llm_sport_category,
                )

                # Timing: use event start/end dates
                commence_time = event.start_date
                resolution_date = event.end_date

                # Detect league and season for cross-source matching
                league = detect_league(event.title, sport_category=llm_sport_category)
                season = detect_season(event.title, league, resolution_date)

                # For Olympics, use specific discipline as category.
                # For sports markets, use detect_market_type for specificity
                # (e.g., "al_cy_young" instead of generic "championship")
                canon_category = detect_market_type(event.title)
                if llm_sport_category == "olympics":
                    discipline = extract_olympic_discipline(event.title)
                    if discipline:
                        canon_category = discipline
                canonical_key = compute_canonical_market_key(
                    llm_sport_category, league, canon_category, season,
                )

                # Generate category tags
                tags = generate_category_tags(
                    event.title, llm_sport_category, league, category,
                )

                # Always assign group_id so markets can be grouped for calibration,
                # feed dedup, and category pages. Single-market events get group_id
                # too — the calibration query's group_size >= 3 threshold naturally
                # ignores groups of size 1.
                poly_group_id = f"polymarket:{event.id}"
                if event.neg_risk:
                    poly_group_type = "negrisk"
                elif len(event.markets) > 1:
                    poly_group_type = "polymarket_event"
                else:
                    poly_group_type = "polymarket_single"

                # Build market_metadata with event-level context
                poly_metadata: dict = {}
                if event.id:
                    poly_metadata["polymarket_event_id"] = event.id
                if event.title:
                    poly_metadata["event_title"] = event.title
                # #8636: the venue's league code rides the slug; see
                # `app.utils.venue_competition`. Rewritten on conflict like the
                # rest of this dict, so live rows acquire it on the next poll.
                if event.slug:
                    poly_metadata[POLYMARKET_EVENT_SLUG_KEY] = event.slug
                # #4965: THE VENUE'S OWN FIXTURE INSTANT, kept because
                # `commence_time` above cannot carry it — that column is fed by
                # Gamma's `startDate`, which is the LISTING stamp (the three
                # Rangers/Mariners fixtures all read 13:00Z on the day each was
                # listed). Without this the matcher has no signal that tells one
                # date of a series from the next, and it linked three of them to
                # one event row. Stored rather than written over `commence_time`
                # because that column has many other readers; the linkage guard
                # is the one that needs the truth, so the truth goes where only
                # it looks. No backfill task: `market_metadata` is rewritten on
                # the on-conflict path below, so every existing row picks this up
                # on the next hourly poll.
                if event.game_start_time:
                    poly_metadata["venue_game_start"] = (
                        event.game_start_time.isoformat()
                    )
                if event.neg_risk:
                    poly_metadata["neg_risk"] = True
                if len(event.markets) > 1:
                    poly_metadata["market_count"] = len(event.markets)
                # Q460: a single-market event's PARENT row is the market, so it
                # is the row the CLOB socket must subscribe by. Multi-market
                # events get theirs per sub-market in the loop below; the parent
                # there is only a group anchor and has no asset id of its own.
                if len(event.markets) == 1:
                    _single_tokens = getattr(event.markets[0], "clob_token_ids", None)
                    if _single_tokens:
                        poly_metadata["clob_token_ids"] = [
                            str(t) for t in _single_tokens if str(t)
                        ]

                # CU-1 clause (2) (#5273), CERT-2733's repair. OUTSIDE the
                # single-market branch above, deliberately: `_parent_outcome_data`
                # below prices the parent in every shape, and the sub-market loop
                # runs for only one of the three — so the children's stamp leaves
                # the parent untyped whatever shape it is, and for a one-market or
                # negrisk event the parent is the row that actually speaks.
                stamp_parent_content_understanding(
                    poly_metadata, event, sport=llm_sport_category
                )

                # #173/#1024: matchup-title write-hook AT INGEST. A game event's
                # decomposed sub-markets (spread/prop rows) don't name both
                # participants in their own `name` (gotcha #18), so the grammar
                # adapter yields ZERO participants and the poly market_event
                # shadow link can't be reproduced. The one-shot backfill stamped
                # `market_metadata['matchup_title']` after the fact, but new rows
                # ingested since got NOTHING until a manual re-run — the 0%-on-
                # new-rows gap. Recover the group matchup from the sibling names
                # (source-native, non-circular — a moneyline/O-U sibling names
                # "A vs. B") and stamp it here so fresh rows carry it at birth.
                # None for non-game groups (no "vs" sibling), so it's a no-op for
                # awards/negrisk questions.
                _group_matchup_title = None
                if len(event.markets) > 1:
                    from app.utils.polymarket_matchup_backfill import (
                        group_matchup as _group_matchup,
                    )
                    _group_matchup_title = _group_matchup(
                        [event.title or ""] + [m.question or "" for m in event.markets]
                    )
                    if _group_matchup_title:
                        poly_metadata["matchup_title"] = _group_matchup_title

                # Aggregate volume/liquidity from event + markets
                poly_volume = int(event.volume) if event.volume else None
                poly_liquidity = float(event.liquidity) if event.liquidity else None
                poly_volume_24h = sum(
                    int(m.volume_24h or 0) for m in event.markets
                ) or None

                _editorial = _matches_editorial_recall(event.title)

                # #6734, THE PARENT HALF. `submarket_is_open` below fixed this
                # same expression for the decomposed CHILD rows, and its
                # docstring names this case in as many words: this function is
                # fed by a `closed=True` tag sweep (the hourly poll, ~:1083) as
                # well as by the open poll, and Gamma keeps `active=true` on a
                # CLOSED event. The child writer was tightened; the parent
                # writer on these lines was not.
                #
                # Measured 2026-09-18 on the specimen's own event: Gamma event
                # 14366 ("Next Republican House Conference Chair?") answers
                # `closed=true, active=true, endDate=2025-06-30` — settled for
                # fifteen months, six legs terminal. Read off `active` alone it
                # was re-stamped `open` every hour, `settled_at` nulled on the
                # line below, and the resolver's `resolution_gate` stamp dropped
                # by `preserve_venue_settled`'s REPLACE. The sweep re-resolved
                # it; the next poll re-opened it. It oscillated rather than
                # converging, which is why every measurement of the RESOLVER
                # came back clean.
                #
                # Cost, the reason this is not cosmetic: 842 markets sitting
                # `open` with EVERY outcome already graded `api_settlement`.
                # Sampled 20 of them at random and asked Gamma directly — 19
                # answered `closed=true`, and all 19 of those still carried
                # `active=true`. The 20th ("Which artists will release new
                # albums in 2026?") is genuinely open with one settled leg, and
                # the predicate below correctly leaves it alone; that is the
                # control, not a miss.
                #
                # Counting note, because the obvious query overstates this: a
                # market with ANY graded outcome numbers 1,257, but 415 of those
                # are live questions with one leg settled. And `settled_at IS
                # NULL` holds for every `open` row by construction of the branch
                # below, so it is a tautology here, not a fingerprint — the
                # fully-graded count is the honest one.
                #
                # `sunk_event_is_open` is the predicate the recovery path
                # already applies for exactly this reason, so it is reused here
                # rather than restated — two copies of one venue rule drift.
                #
                # STRICTLY TIGHTENING, like the child fix: it adds ways to be
                # `resolved` and removes none, so it can never turn a stored
                # `resolved` back into `open`. `status` gates
                # `/api/futures/{categories,faceted,grouped-feed,movers}`, so
                # the only movement it can cause is rows leaving those surfaces
                # — never a settled market being pushed onto one.
                _venue_open = sunk_event_is_open(event)

                # Build update set for on-conflict
                update_set = {
                    "name": event.title,
                    "market_tier": market_tier,
                    "llm_league": league,
                    "canonical_market_key": canonical_key,
                    "commence_time": commence_time,
                    "resolution_date": resolution_date,
                    "status": "open" if _venue_open else "resolved",
                    # LINKLOSS-02: the stamp is coupled to the status in the
                    # SAME statement. This poll rewrites `status` every hour and
                    # can flip a market back to 'open', so a stamp written
                    # anywhere else would survive the reopen. Resolved keeps the
                    # FIRST observation; open clears it.
                    "settled_at": (
                        None if _venue_open
                        else func.coalesce(FuturesMarket.settled_at, func.now())
                    ),
                    "category_tags": tags,
                    "group_id": poly_group_id,
                    "group_type": poly_group_type,
                    "group_position": 0,
                    # #2222: see the kalshi poll's twin of this line. A REPLACE
                    # drops the venue-settled stamp; merge it back so the bound
                    # does not depend on this poll never reaching the market.
                    "market_metadata": preserve_venue_settled(
                        poly_metadata if poly_metadata else None,
                        FuturesMarket.market_metadata,
                    ),
                    "updated_at": func.now(),
                    "volume": poly_volume,
                    "volume_24h": poly_volume_24h,
                    "liquidity": poly_liquidity,
                    "volume_updated_at": func.now(),
                    "is_editorial_recall": _editorial,
                }
                # Only update llm_sport_category if we have a non-"other" value
                if llm_sport_category and llm_sport_category != "other":
                    update_set["llm_sport_category"] = llm_sport_category

                # #5516 — `category` IS OTHERWISE INSERT-ONLY ON THIS ROW, which
                # is the entire reason 120 open inning props still badge
                # Championship: they were born before the fix and this writer has
                # never had a way to say otherwise. `market_tier` sits in
                # `update_set` above, which is how #6471 propagated within one
                # poll; `category` does not, so without this line the fix reaches
                # only rows minted from here on and the reader sees nothing for
                # the life of every row already open.
                #
                # WRITTEN ONLY WHEN THE OVERRIDE ACTUALLY FIRED — never as an
                # unconditional `"category": category`. That version would hand
                # every future re-poll authority over a column with a repair task
                # and an LLM behind it (`repair_polymarket_sport_category`,
                # `repair_polymarket_senate_category`), quietly reverting their
                # work on 32,554 open rows every hour. This one writes
                # `game_prop`, on rows whose own name says so, and nothing else:
                # the blast radius is the predicate's, measured at 201 open rows
                # (120 baseball, 48 football, 33 cricket; production 2026-09-19).
                if _category_corrected:
                    update_set["category"] = category

                # Upsert FuturesMarket
                market_stmt = pg_insert(FuturesMarket).values(
                    source="polymarket",
                    external_id=event.id,
                    name=event.title,
                    category=category,
                    llm_sport_category=llm_sport_category,
                    llm_league=league,
                    canonical_market_key=canonical_key,
                    market_tier=market_tier,
                    mutually_exclusive=event.neg_risk,
                    commence_time=commence_time,
                    resolution_date=resolution_date,
                    # Same rule on the INSERT arm: a parent first seen through
                    # the `closed=True` sweep must not be born `open`.
                    status="open" if _venue_open else "resolved",
                    category_tags=tags,
                    group_id=poly_group_id,
                    group_type=poly_group_type,
                    group_position=0,
                    market_metadata=poly_metadata if poly_metadata else None,
                    volume=poly_volume,
                    volume_24h=poly_volume_24h,
                    liquidity=poly_liquidity,
                    volume_updated_at=func.now(),
                    is_editorial_recall=_editorial,
                ).on_conflict_do_update(
                    index_elements=["source", "external_id"],
                    set_=update_set,
                ).returning(FuturesMarket.id)

                result = await session.execute(market_stmt)
                futures_market_id = result.scalar_one()
                stats["events_processed"] += 1

                # Collect outcome data for ranking. One function for all three
                # event shapes (#3613) so the refresh pass that re-reads a dark
                # market cannot price it differently from this poll.
                outcome_data = _parent_outcome_data(event)

                if not event.neg_risk and len(event.markets) > 1:
                    # Game-level event: each sub-market (moneyline, spread, O/U,
                    # player props) becomes its own FuturesMarket row. Without this,
                    # all 40 sub-markets are flattened into outcomes of a single
                    # FuturesMarket, making player props invisible to the game-markets
                    # endpoint (which classifies by market name, not outcome name).
                    #
                    # The parent FuturesMarket (created above) serves as the group
                    # anchor. Each sub-market inherits its event_id, sport category,
                    # and group_id for linkage.
                    parent_market_id = futures_market_id

                    # Check if parent is already linked to an event
                    _parent_eid_r = await session.execute(
                        select(FuturesMarket.event_id).where(FuturesMarket.id == parent_market_id)
                    )
                    parent_event_id = _parent_eid_r.scalar_one_or_none()

                    for market in event.markets:
                        prob, prob_source = _resolve_market_probability_with_source(market)

                        if prob is None or prob <= 0:
                            continue

                        sub_name = market.question or event.title
                        sub_tier = compute_market_tier(sub_name, category, sport_category=llm_sport_category)

                        # #173/#1024: stamp the group matchup title onto every
                        # sub-market of a game group at ingest. On conflict, MERGE
                        # into existing metadata (never clobber) with the same
                        # COALESCE(md,'{}') || jsonb_build_object idiom the backfill
                        # uses, so re-ingests and prior backfills stay idempotent.
                        # Queue 390 Item 2a: stamp the event id the loop is already
                        # holding. `event.id` is right there — the parent row above
                        # writes it from the same variable — and dropping it here is
                        # what made 64.8% of a 48h mint bare-hex `no_eid`.
                        sub_meta_insert = sub_market_metadata(
                            event_id=event.id,
                            matchup_title=_group_matchup_title,
                            # Q460: the CLOB WebSocket's subscription key. Absent
                            # on all 687 live/upcoming rows measured 2026-08-30,
                            # which is why the Polymarket fast lane never ran.
                            clob_token_ids=getattr(market, "clob_token_ids", None),
                            # CU-1 clause (2) (#5273): our reading of the
                            # question, plus Gamma's own label for it, which
                            # clause (4) parsed onto the DTO and nothing stored.
                            # `sub_name` is the exact string the row is named
                            # with, so the stored type describes the row a
                            # reader sees rather than a title we discarded.
                            content_understanding=build_content_understanding(
                                name=sub_name,
                                external_id=market.condition_id,
                                sport=llm_sport_category,
                                sports_market_type=getattr(
                                    market, "sports_market_type", None
                                ),
                            ),
                            # #6073: the venue's own fixture instant, which the
                            # parent row above already stamps from this same
                            # variable. The child is the row the event is minted
                            # from, so without it a match is dated by the moment
                            # Polymarket listed it and reads LIVE hours early.
                            venue_game_start=event.game_start_time,
                            # #8636: the venue's league code, for placement.
                            event_slug=event.slug,
                        )
                        # ── ITS OWN 24h VOLUME (UX-P157, #2256).
                        #
                        # The PARENT event row has carried `volume_24h` since it
                        # was written; the sub-market row never has, and the
                        # sub-market is the one a question is asked of. Measured
                        # 2026-08-28 against production: all 336 US Open
                        # reach-a-round markets — every cell of the bracket
                        # grid — hold `volume_24h IS NULL`, while their parent
                        # event rows hold real figures (`910235` = $5,493).
                        #
                        # The consequence was not a missing column, it was a
                        # missing GRADE. Alex's illiquidity ruling asks for at
                        # least two levels and `market_liquidity` builds them
                        # from two facts; with this one absent, every cell on
                        # the surface the ruling is about could only ever reach
                        # level one. A graded signal with one reachable grade is
                        # not a graded signal.
                        #
                        # `market.volume_24h` is Gamma's own `volume24hr`, already
                        # parsed by `PolymarketMarket` and already in this loop's
                        # hand — this writes down a number we were throwing away,
                        # and it adds no request. NULL-preserving: a market Gamma
                        # serves without the field keeps NULL, which grades as
                        # unknown and draws nothing, rather than a fabricated 0
                        # that would read downstream as a measured "nobody traded
                        # this".
                        sub_volume_24h = (
                            int(market.volume_24h)
                            if market.volume_24h is not None
                            else None
                        )
                        # #6734: this row IS `market`, so its openness is the
                        # market's own — not the parent event's `active`. See
                        # `submarket_is_open`; the two insert/update sites below
                        # share this one value so an upsert cannot disagree with
                        # itself about whether the leg still trades.
                        sub_open = submarket_is_open(event, market)
                        # #2027: the second signal the opening gates never
                        # asked for. A sub-market first seen through the
                        # `closed=True` sweep (or past its resolution_date)
                        # quotes the settled book, not a price — stamping it
                        # as the opening is the hindsight capture.
                        # #8466: the leg's OWN date, not the parent's — a leg
                        # past its own end is hindsight even while its event
                        # runs, and one ending after the event is not.
                        sub_resolution_date = submarket_resolution_date(
                            event, market
                        )
                        _sub_hindsight = opening_capture_is_hindsight(
                            event, market, sub_resolution_date, now
                        )
                        sub_set = {
                            "name": sub_name,
                            "market_tier": sub_tier,
                            "status": "open" if sub_open else "resolved",
                            # Same coupling as the parent above (LINKLOSS-02).
                            "settled_at": (
                                None if sub_open
                                else func.coalesce(
                                    FuturesMarket.settled_at, func.now()
                                )
                            ),
                            "updated_at": func.now(),
                            "volume_24h": sub_volume_24h,
                            "volume_updated_at": func.now(),
                        }
                        # #8466: repair the leg's date on re-ingest, but only an
                        # OPEN leg Gamma dates itself. A settled leg keeps the
                        # date its calibration closing line was drawn against,
                        # and a leg with no date of its own keeps what it has.
                        if sub_open and getattr(market, "end_date", None) is not None:
                            sub_set["resolution_date"] = market.end_date
                        # #8430: the parent's link, never the parent's ABSENCE of
                        # one. A game container is rejected by the matcher as a
                        # `parent_row`, so for most groups `parent_event_id` is
                        # NULL for life — and writing that NULL on conflict wiped
                        # the link the matcher had made on each child, every
                        # poll. The matcher then re-linked them five minutes
                        # later, and where its best candidate was refused it
                        # minted a fresh row per child per hour: Boyer v Gorzny
                        # became 14 rows, 11 of them empty and reading LIVE.
                        # Measured 2026-09-24: 3,321 children (534 groups) sat
                        # linked under an unlinked parent. A child that is wrong
                        # for its own event is Phase 1.5's to unlink — it walks
                        # every linked open market, children included.
                        if parent_event_id is not None:
                            sub_set["event_id"] = parent_event_id
                        # Q493: repair the sport on RE-INGEST, not only at birth.
                        # The parent's `update_set` has always carried this and
                        # the sub-market's never did, so a group whose sport was
                        # corrected kept its children on the stale value forever
                        # — 306 of the 639 mis-filed US Open rows measured on
                        # `c3143bc2` were children. Same guard as the parent:
                        # never overwrite a real value with the "other" default.
                        if llm_sport_category and llm_sport_category != "other":
                            sub_set["llm_sport_category"] = llm_sport_category
                        if sub_meta_insert:
                            # MERGE, never clobber — same COALESCE(md,'{}') || idiom
                            # the backfill uses, so re-ingests and prior backfills
                            # stay idempotent (#173/#1024).
                            #
                            # The merge now covers the event id too, which means a
                            # re-ingest REPAIRS an existing bare-hex row rather than
                            # only fixing rows minted from here on. Polymarket
                            # re-serves open events continuously, so this recovers a
                            # slice of the historical class for free — the one-shot
                            # group_id backfill still owns the rest, including every
                            # row whose event has since closed.
                            import json as _json
                            from sqlalchemy import cast as _sa_cast, literal as _sa_literal
                            from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
                            _sub_meta_pairs: list = []
                            for _k, _v in sub_meta_insert.items():
                                if isinstance(_v, (list, dict)):
                                    # `jsonb_build_object` takes SQL scalars; a
                                    # bound Python list arrives as a Postgres
                                    # ARRAY, not a JSON array, and the key comes
                                    # back shaped wrong (or the bind refuses).
                                    # Serialise and cast so the merged value is
                                    # the same JSON the plain insert writes.
                                    _v = _sa_cast(
                                        _sa_literal(_json.dumps(_v)), _PG_JSONB,
                                    )
                                _sub_meta_pairs.extend([_k, _v])
                            sub_set["market_metadata"] = func.coalesce(
                                FuturesMarket.market_metadata,
                                _sa_cast(_sa_literal("{}"), _PG_JSONB),
                            ).op("||")(
                                func.jsonb_build_object(*_sub_meta_pairs)
                            )

                        sub_stmt = pg_insert(FuturesMarket).values(
                            source="polymarket",
                            external_id=market.condition_id,
                            name=sub_name,
                            category="game_prop",
                            llm_sport_category=llm_sport_category,
                            llm_league=league,
                            market_tier=sub_tier,
                            mutually_exclusive=True,
                            commence_time=commence_time,
                            resolution_date=sub_resolution_date,
                            status="open" if sub_open else "resolved",
                            group_id=poly_group_id,
                            group_type="polymarket_sub_market",
                            event_id=parent_event_id,
                            market_metadata=sub_meta_insert,
                            volume_24h=sub_volume_24h,
                            volume_updated_at=func.now(),
                        ).on_conflict_do_update(
                            index_elements=["source", "external_id"],
                            set_=sub_set,
                        ).returning(FuturesMarket.id)

                        sub_result = await session.execute(sub_stmt)
                        sub_market_id = sub_result.scalar_one()

                        # Create Over/Yes outcome
                        over_fallback = "Over" if "o/u" in sub_name.lower() else "Yes"
                        over_name = _sub_market_side_label(
                            market,
                            0,
                            sub_name,
                            over_fallback,
                        )
                        over_american = probability_to_american(prob) if 0 < prob < 1 else None

                        sub_has_trading = (
                            market.best_bid is not None and market.best_bid > 0
                        ) or (
                            market.last_trade_price is not None and market.last_trade_price > 0
                        )
                        # An opening only makes sense at a real, non-degenerate price.
                        # A price of exactly 0.0/1.0 is a settled/placeholder value, not a
                        # tradeable opening — stamping it produced the impossible
                        # both-sides=1.0 binaries (#137 opening artifact).
                        sub_has_open = _is_tradeable_opening(prob, sub_has_trading)

                        # THE PAIR GATE. Both legs of one binary must come from the
                        # same normalised upstream pair and sum to ~1, or NEITHER
                        # leg is stamped as an opening. `opening_probability` is what
                        # `calibration_probability` falls back to, so a leg stamped
                        # from a price whose partner disagrees becomes a published
                        # forecast we are then graded on -- 5,566 such markets exist
                        # and 631 arrived after the 2026-07-08 Under-side fix, because
                        # that fix corrected WHICH price the Under leg copied without
                        # ever checking the two prices against each other.
                        # `app/utils/pair_opening_coherence.py` carries the census.
                        sub_under_raw = (
                            market.outcome_prices[1]
                            if market.outcome_prices and len(market.outcome_prices) > 1
                            else None
                        )
                        sub_pair_verdict = classify_pair_opening(
                            prob, sub_under_raw, price_source=prob_source
                        )
                        if sub_pair_verdict != PAIR_OPENING_OK:
                            stats["pair_opening_refused"] = (
                                stats.get("pair_opening_refused", 0) + 1
                            )
                            stats[f"pair_opening_{sub_pair_verdict}"] = (
                                stats.get(f"pair_opening_{sub_pair_verdict}", 0) + 1
                            )
                            sub_has_open = False

                        # #2027: the settled book is not an opening (ruling
                        # 103). Current price, book and snapshot still write;
                        # only the opening stamp is refused, so the row keeps
                        # its provenance and no existing row is rewritten.
                        if sub_has_open and _sub_hindsight:
                            stats["opening_refused_hindsight"] = (
                                stats.get("opening_refused_hindsight", 0) + 1
                            )
                            sub_has_open = False

                        # THE PRICE GATE (#6793). The gate above governs the number
                        # we are GRADED on; this one governs the number a reader
                        # SEES, and until now nothing did. Same module, same
                        # tolerance, one clause different (provenance is not tested
                        # — see `classify_pair_price`), because a last trade is an
                        # honest current price and a dishonest opening.
                        #
                        # Measured on production 2026-09-17: 8,962 open two-leg
                        # decomposed pairs, 282 not summing to 1, 152 of them live.
                        # SIX are served to a reader as both halves of the
                        # contradiction (`Dawson Knox: Anytime Touchdown` at No 90%
                        # / Yes 15%; `Galaxy vs Rapids O/U 8.5` at Under 50% / Over
                        # 47.5%) — serve hides the rest by other means. But ALL 152
                        # carry snapshots (3,437 rows, 552 in 24h) and
                        # `calibration_probability` reads snapshots before it falls
                        # back to the opening, so the graded half is the whole 152
                        # and it has no serve-time rescue at all.
                        #
                        # ONLY ASKED OF AN ACTUAL PAIR. A market with no second leg
                        # has nothing to contradict, and `classify_pair_price` fails
                        # closed on a None partner by design, so asking it here
                        # would blank every one-sided market on the venue.
                        sub_price_ok = True
                        if sub_under_raw is not None:
                            sub_price_verdict = classify_pair_price(
                                prob, sub_under_raw
                            )
                            if sub_price_verdict != PAIR_OPENING_OK:
                                sub_price_ok = False
                                stats["pair_price_refused"] = (
                                    stats.get("pair_price_refused", 0) + 1
                                )
                                stats[f"pair_price_{sub_price_verdict}"] = (
                                    stats.get(f"pair_price_{sub_price_verdict}", 0) + 1
                                )

                        # What the two upserts below actually store. NULL rather
                        # than a repair: `current_probability` is nullable and
                        # 6,530 of 59,333 live Polymarket legs already carry NULL,
                        # `has_no_real_price` reads NULL as "no price" and drops the
                        # card, and synthesising either leg from its partner would
                        # assert a level nobody quoted (the reasoning
                        # `pair_opening_coherence` already records for the opening
                        # half, and which its own guard test pins by refusing to let
                        # that arithmetic appear in this block at all).
                        #
                        # The BOOK is still written on both legs. A refusal says the
                        # two derived probabilities disagree; it says nothing against
                        # the quotes, which are what the venue actually published and
                        # what every book-based predicate downstream reads.
                        sub_over_price = prob if sub_price_ok else None
                        sub_over_american = over_american if sub_price_ok else None

                        sub_opening = prob if sub_has_open else None
                        sub_opening_am = over_american if sub_has_open else None
                        sub_opening_at = now if sub_has_open else None

                        # Forward-capture per-outcome volume so the traded/untraded
                        # calibration tag stays populated without a re-backfill.
                        # fo.volume is Integer — cap to avoid overflow on the
                        # multi-billion-dollar markets.
                        sub_vol = (
                            min(int(market.volume), 2_000_000_000)
                            if getattr(market, "volume", None)
                            else None
                        )

                        over_update: dict = {
                            "current_probability": sub_over_price,
                            "current_american_odds": sub_over_american,
                            "current_yes_bid": market.best_bid,
                            "current_yes_ask": market.best_ask,
                            "rank": 1,
                            "volume": sub_vol,
                            "last_updated": func.now(),
                        }
                        # #6793: a move and a change-stamp are claims ABOUT a price.
                        # Computing either against a refused leg would subtract from
                        # NULL (silently nulling the delta) and, worse, advance
                        # `price_changed_at` for a price we declined to store — a
                        # freshness stamp on an absence. Both keys are therefore
                        # omitted on refusal, leaving the prior values untouched.
                        if sub_price_ok:
                            over_update["probability_change_24h"] = (
                                prob - FuturesOutcome.current_probability
                            )
                            over_update["price_changed_at"] = price_changed_at_value(  # #2024
                                FuturesOutcome.current_probability,
                                FuturesOutcome.price_changed_at,
                                prob,
                            )
                        if sub_has_open:
                            over_update["opening_probability"] = func.coalesce(
                                FuturesOutcome.opening_probability, prob
                            )
                        _carry_venue_side_name(over_update, over_name, over_fallback)

                        over_stmt = pg_insert(FuturesOutcome).values(
                            market_id=sub_market_id,
                            external_id=f"{market.condition_id}_yes",
                            name=over_name,
                            current_probability=sub_over_price,
                            current_american_odds=sub_over_american,
                            current_yes_bid=market.best_bid,
                            current_yes_ask=market.best_ask,
                            opening_probability=sub_opening,
                            opening_american_odds=sub_opening_am,
                            opening_captured_at=sub_opening_at,
                            rank=1,
                            volume=sub_vol,
                            # Explicit, and load-bearing: the column is
                            # `boolean NULL DEFAULT false`, so an INSERT that
                            # omits it stores an affirmative graded LOSS
                            # (CAL-P1004R) on a leg nobody called. #4788.
                            is_winner=None,
                            resolution_source=None,
                        ).on_conflict_do_update(
                            index_elements=["market_id", "external_id"],
                            set_=over_update,
                        ).returning(FuturesOutcome.id)

                        over_result = await session.execute(over_stmt)
                        over_outcome_id = over_result.scalar_one()

                        # #6793: SKIPPED, not nulled — `FuturesOddsSnapshot.probability`
                        # is NOT NULL, so a refused pair has no honest row to write
                        # here. This is the half calibration grades on
                        # (`calibration_probability` is read from snapshots before it
                        # falls back to the opening), which makes it the half where
                        # storing an incoherent price costs the most and the one the
                        # opening gate never protected.
                        if sub_price_ok:
                            snap_stmt = pg_insert(FuturesOddsSnapshot).values(
                                outcome_id=over_outcome_id,
                                bookmaker="polymarket",
                                probability=prob,
                                american_odds=over_american,
                                yes_bid=market.best_bid,
                                yes_ask=market.best_ask,
                                last_price=market.last_trade_price,
                                captured_at=now,
                            )
                            await session.execute(snap_stmt)

                        # Create Under/No outcome if available
                        if len(market.outcome_prices) > 1:
                            under_prob = market.outcome_prices[1]
                            under_fallback = "Under" if "o/u" in sub_name.lower() else "No"
                            under_name = _sub_market_side_label(
                                market,
                                1,
                                sub_name,
                                under_fallback,
                            )
                            under_american = probability_to_american(under_prob) if 0 < under_prob < 1 else None

                            # The Under/No side must open at ITS OWN price, not the
                            # Over/Yes price. Using `sub_opening` (the over prob) here
                            # made every Under outcome store the over-side probability,
                            # so calibration_probability (which falls back to
                            # opening_probability when no snapshot exists) inherited the
                            # wrong side — the #137 poly-Under sign-flip class.
                            sub_under_has_open = _is_tradeable_opening(
                                under_prob, sub_has_trading
                            ) and sub_pair_verdict == PAIR_OPENING_OK
                            # #2027: same refusal as the Over leg above —
                            # the settled book is not an opening.
                            if sub_under_has_open and _sub_hindsight:
                                stats["opening_refused_hindsight"] = (
                                    stats.get("opening_refused_hindsight", 0) + 1
                                )
                                sub_under_has_open = False
                            sub_under_opening = under_prob if sub_under_has_open else None
                            # These two used to be gated on the OVER leg's
                            # `sub_opening_at` and on bare `sub_has_trading`, so an
                            # Under leg could carry an opening with no capture
                            # timestamp (breaking every capture-age read of it) or a
                            # timestamp and American odds with no opening at all.
                            # One leg, one gate.
                            sub_under_opening_am = (
                                under_american if sub_under_has_open else None
                            )
                            sub_under_opening_at = now if sub_under_has_open else None

                            # CAL-P095: the Under leg's book. Measured
                            # population-wide before this line existed —
                            # 493,415 Under/No legs, ZERO with a bid or an ask,
                            # against 99.14% ask coverage on their Over
                            # partners — because these two columns were on the
                            # Over upsert and on nothing else. That made every
                            # book-based phantom predicate blind on half of
                            # each pair (#1578, #1574), and it made
                            # `no_book` look like a fact about the market when
                            # it was a fact about this writer (gotcha #53).
                            # The No token's book is the Yes token's book from
                            # the other side, so this records what exists
                            # rather than inventing one; NULL in, NULL out.
                            #
                            # CAL-P097 (#2212, CERT-403C): the SNAPSHOT half now
                            # ships too, and the third return value is no longer
                            # discarded. CAL-P095 deliberately stopped at the
                            # outcome columns and said so here, because
                            # POLY_PLACEHOLDER_EXCLUDE in
                            # precompute_calibration.py reads exactly the
                            # snapshot columns and filling them moves a
                            # published number. That deferral was correct and it
                            # is now discharged the way it asked to be: the
                            # staged spec is graded, Option A is recorded as a
                            # named decision (see the module docstring's
                            # UNDER-LEG SNAPSHOT BOOK note), and the release is
                            # FORWARD-ONLY — new snapshots only, no historical
                            # row is un-excluded and no re-grade happens
                            # anywhere (gotcha #21).
                            under_best_bid, under_best_ask, under_last = (
                                complementary_book(
                                    market.best_bid,
                                    market.best_ask,
                                    market.last_trade_price,
                                )
                            )

                            # #6793: the same refusal, applied to the partner leg.
                            # Symmetric because the verdict is about the PAIR — the
                            # module's own doctrine is that keeping the
                            # coherent-looking side leaves a number with no partner
                            # to check it against, which is how the `partial_open`
                            # population came to exist.
                            sub_under_price = under_prob if sub_price_ok else None
                            sub_under_american = (
                                under_american if sub_price_ok else None
                            )

                            under_update: dict = {
                                "current_probability": sub_under_price,
                                "current_american_odds": sub_under_american,
                                "current_yes_bid": under_best_bid,
                                "current_yes_ask": under_best_ask,
                                "rank": 2,
                                "volume": sub_vol,
                                "last_updated": func.now(),
                            }
                            if sub_price_ok:
                                under_update["price_changed_at"] = price_changed_at_value(  # #2024
                                    FuturesOutcome.current_probability,
                                    FuturesOutcome.price_changed_at,
                                    under_prob,
                                )
                            if sub_under_has_open:
                                under_update["opening_probability"] = func.coalesce(
                                    FuturesOutcome.opening_probability, under_prob
                                )
                            _carry_venue_side_name(
                                under_update, under_name, under_fallback
                            )

                            under_stmt = pg_insert(FuturesOutcome).values(
                                market_id=sub_market_id,
                                external_id=f"{market.condition_id}_no",
                                name=under_name,
                                current_probability=sub_under_price,
                                current_american_odds=sub_under_american,
                                current_yes_bid=under_best_bid,
                                current_yes_ask=under_best_ask,
                                opening_probability=sub_under_opening,
                                opening_american_odds=sub_under_opening_am,
                                opening_captured_at=sub_under_opening_at,
                                rank=2,
                                volume=sub_vol,
                                # Explicit, and load-bearing: the column is
                                # `boolean NULL DEFAULT false`, so an INSERT
                                # that omits it stores an affirmative graded
                                # LOSS (CAL-P1004R) on a leg nobody called.
                                # #4788.
                                is_winner=None,
                                resolution_source=None,
                            ).on_conflict_do_update(
                                index_elements=["market_id", "external_id"],
                                set_=under_update,
                            ).returning(FuturesOutcome.id)
                            under_result = await session.execute(under_stmt)
                            under_outcome_id = under_result.scalar_one()

                            # Write a snapshot for the Under side too (the Over side
                            # gets one above). Without this the Under outcome has no
                            # price history and calibration_probability falls back to
                            # opening_probability — the root of the sign-flip class.
                            # CAL-P097 (#2212): the three book columns the Over
                            # snapshot 100 lines up has always carried. Their
                            # absence here was not a liquidity fact about Under
                            # legs, it was this writer never mentioning the
                            # columns — 493,415 Under/No legs with zero books
                            # against 99.14% ask coverage on their Over
                            # partners. POLY_PLACEHOLDER_EXCLUDE's `NOT EXISTS
                            # (... yes_bid > 0 OR last_price > 0)` therefore
                            # fired on almost every Under leg regardless of
                            # whether the market traded: 95.09% of Under band
                            # legs excluded against 0.41% of Over, a 232x
                            # asymmetry that kept the +7.50 pp half of each
                            # binary and discarded the -7.54 pp half.
                            #
                            # The values come from `complementary_book`, NOT
                            # from a second call and NOT restated: same helper,
                            # same call, same tuple as the outcome upsert above,
                            # so the two can never disagree about one market.
                            # #6793: skipped on a refused pair, exactly as the Over
                            # snapshot above is, and for the same NOT NULL reason.
                            if sub_price_ok:
                                under_snap_stmt = pg_insert(FuturesOddsSnapshot).values(
                                    outcome_id=under_outcome_id,
                                    bookmaker="polymarket",
                                    probability=under_prob,
                                    american_odds=under_american,
                                    yes_bid=under_best_bid,
                                    yes_ask=under_best_ask,
                                    last_price=under_last,
                                    captured_at=now,
                                )
                                await session.execute(under_snap_stmt)

                        stats["markets_processed"] += 1
                        stats["outcomes_updated"] += 2
                        # #6793: a refused pair writes no snapshot, so counting one
                        # here would report captured prices that do not exist — the
                        # task-verdict failure mode of gotcha #53 ("it returned" is
                        # not "it worked"). The outcome rows ARE still written (their
                        # books and names), so that counter is unchanged.
                        if sub_price_ok:
                            stats["snapshots_created"] += 1
                        stats["sub_markets_created"] = stats.get("sub_markets_created", 0) + 1

                # The parent's own legs for this shape were built by
                # `_parent_outcome_data` above, before the branch.

                # CAL-P006 (#1527): an impossible field is not a price — refuse it
                # at CAPTURE rather than storing it and repairing it later.
                #
                # negRisk means a single-winner partition, so two legs cannot both
                # be near-certain. Gamma nonetheless answers 1.00 on EVERY leg for
                # some long-settled events: 111 Europa League 1X2 markets sat at
                # Home 1.00 / Away 1.00 / Draw 1.00, a field summing to 300%,
                # re-stamped on every poll (72 consecutive snapshots, all 1.0).
                #
                # Per-leg guards cannot catch this and should not try —
                # ``_resolve_market_probability`` is permissive at the extremes on
                # purpose, because ONE near-certain leg is exactly what a settled
                # market looks like. Only the field view shows the contradiction.
                #
                # Skipping is not caution, it is correctness: there is no reading
                # of this field that is a real price. It also protects the one
                # field that never gets a second chance — a market first seen after
                # settlement captures 1.00 as its opening_probability and, because
                # opening is COALESCEd, keeps it forever.
                if field_is_incoherent(
                    (od["prob"] for od in outcome_data),
                    mutually_exclusive=bool(event.neg_risk),
                ):
                    stats["incoherent_fields_skipped"] = (
                        stats.get("incoherent_fields_skipped", 0) + 1
                    )
                    logger.warning(
                        "Polymarket event %s (%s): %d/%d legs near-certain on a "
                        "negRisk single-winner field — refusing to capture "
                        "(#1527)",
                        event.id, (event.title or "")[:80],
                        count_near_certain(od["prob"] for od in outcome_data),
                        len(outcome_data),
                    )
                    continue

                # Sort by probability descending to compute ranks
                outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                # Upsert outcomes with ranks
                for rank, od in enumerate(outcome_data, 1):
                    prob = od["prob"]
                    american = probability_to_american(prob) if 0 < prob < 1 else None
                    stats["markets_processed"] += 1

                    # Only set opening_probability when there's real trading.
                    # A wide bid-ask spread or no bids means placeholder pricing.
                    has_real_trading = (
                        od["yes_bid"] is not None
                        and od["yes_bid"] > 0
                        and od["yes_ask"] is not None
                        and (od["yes_ask"] - od["yes_bid"]) < 0.50
                    ) or (
                        od.get("last_price") is not None and od["last_price"] > 0
                    )
                    # #2027: the parent-field twin of the sub-market refusal
                    # above. `_process_event_batch` is fed by the `closed=True`
                    # settled-sports sweep as well as the open poll, so a
                    # settled quote with a last trade behind it passes the
                    # liquidity test — and is still the answer, not a price
                    # (ruling 103). Current price, book and snapshot still
                    # write; only the opening stamp is refused.
                    #
                    # CERT-3202: this passed `market=None` and so asked only
                    # whether the PARENT was closed. A Polymarket event stays
                    # open while its children settle one by one, so a closed
                    # child under an open parent — including the sole-child
                    # case — banked its settled book as the opening. The leg
                    # carries the sub-market it was priced from, so the refusal
                    # is per leg and a mixed field refuses only its settled
                    # legs while its live ones still open normally.
                    if has_real_trading and opening_capture_is_hindsight(
                        event, od.get("market"), resolution_date, now
                    ):
                        stats["opening_refused_hindsight"] = (
                            stats.get("opening_refused_hindsight", 0) + 1
                        )
                        has_real_trading = False
                    opening_prob = prob if has_real_trading else None
                    opening_american = american if has_real_trading else None
                    opening_at = now if has_real_trading else None

                    update_set: dict = {
                        "name": od["name"],
                        "current_probability": prob,
                        "current_american_odds": american,
                        "current_yes_bid": od["yes_bid"],
                        "current_yes_ask": od["yes_ask"],
                        "rank": rank,
                        "probability_change_24h": prob - FuturesOutcome.current_probability,
                        "rank_change_24h": FuturesOutcome.rank - rank,
                        "last_updated": func.now(),
                        "price_changed_at": price_changed_at_value(  # #2024
                            FuturesOutcome.current_probability,
                            FuturesOutcome.price_changed_at,
                            prob,
                        ),
                    }
                    if has_real_trading:
                        update_set["opening_probability"] = func.coalesce(
                            FuturesOutcome.opening_probability, prob
                        )
                        update_set["opening_american_odds"] = func.coalesce(
                            FuturesOutcome.opening_american_odds, american
                        )
                        update_set["opening_captured_at"] = func.coalesce(
                            FuturesOutcome.opening_captured_at, now
                        )

                    outcome_stmt = pg_insert(FuturesOutcome).values(
                        market_id=futures_market_id,
                        external_id=od["external_id"],
                        name=od["name"],
                        current_probability=prob,
                        current_american_odds=american,
                        current_yes_bid=od["yes_bid"],
                        current_yes_ask=od["yes_ask"],
                        opening_probability=opening_prob,
                        opening_american_odds=opening_american,
                        opening_captured_at=opening_at,
                        rank=rank,
                        # Explicit, and load-bearing: the column is
                        # `boolean NULL DEFAULT false`, so an INSERT that omits
                        # it stores an affirmative graded LOSS (CAL-P1004R) on
                        # a leg nobody called. #4788.
                        is_winner=None,
                        resolution_source=None,
                    ).on_conflict_do_update(
                        index_elements=["market_id", "external_id"],
                        set_=update_set,
                    ).returning(FuturesOutcome.id)

                    result = await session.execute(outcome_stmt)
                    outcome_id = result.scalar_one()
                    stats["outcomes_updated"] += 1

                    # Create snapshot
                    snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                        outcome_id=outcome_id,
                        bookmaker="polymarket",
                        probability=prob,
                        american_odds=american,
                        yes_bid=od["yes_bid"],
                        yes_ask=od["yes_ask"],
                        last_price=od["last_price"],
                        captured_at=now,
                    )
                    await session.execute(snapshot_stmt)
                    stats["snapshots_created"] += 1

                # #4000: the same pass also learned which legs the venue quotes
                # NO price for. Withdraw our number on those rather than leaving
                # the last one standing — see `_unpriced_leg_external_ids`. Runs
                # after the upsert so a leg that regained a price this pass has
                # already been rewritten and no longer qualifies.
                retired = await _retire_unpriced_legs(
                    session, futures_market_id, _unpriced_leg_external_ids(event)
                )
                if retired:
                    stats["legs_retired"] = stats.get("legs_retired", 0) + retired
                    logger.info(
                        "Polymarket event %s (%s): withdrew our price on %d leg(s) "
                        "the venue quotes no price for (#4000)",
                        event.id, (event.title or "")[:80], retired,
                    )

                # #6598: the ranks written above were derived against THIS
                # BATCH. The batch is not the field — `_retire_unpriced_legs`
                # has just nulled prices without renumbering anyone, and a leg
                # whose book was unreadable this pass never entered
                # `outcome_data` at all and still carries a number from an
                # older, differently-sized field. Re-derive across every leg of
                # the market, last, so it sees the finished state.
                _reranked = (
                    await session.execute(
                        rerank_market_field_stmt(futures_market_id)
                    )
                ).rowcount
                if _reranked:
                    stats["ranks_rederived"] = (
                        stats.get("ranks_rederived", 0) + _reranked
                    )

            except Exception as e:
                stats["errors"].append(f"{event.id}: {str(e)}")
                continue

        # The parent→sub-market event_id sweep used to run HERE, once per batch.
        # It is now `link_polymarket_sub_markets`, called ONCE per poll — see that
        # function's docstring for the measurement and the equivalence argument.
        await session.commit()


# =========================================================================
# Dark linked markets (#3613) — the Polymarket twin of #3518's Kalshi hole
# =========================================================================

#: How far ahead a scheduled event is still worth re-reading, and how long after
#: kick-off a not-yet-flipped row stays in scope. Both MEASURED against the
#: population rather than chosen: on 2026-09-06 every one of the 501 dark linked
#: markets sat inside 14 days (119 within 2 days, 298 at 2-7d, 46 at 7-14d, 38 on
#: live events), so 14 days covers 100% of the work and reaches the 7-14d band
#: that the Kalshi twin's 7-day horizon leaves behind (#3602).
LINKED_POLY_BOOK_HORIZON_DAYS = 14
LINKED_POLY_BOOK_LOOKBACK_HOURS = 6

#: Ids per Gamma request. Same figure as `futures_price_refresh`'s
#: POLYMARKET_ID_BATCH, verified against the live API in #2199; kept as its own
#: constant so this module does not import another task module.
_LINKED_POLY_ID_BATCH = 20

#: Ceiling on markets read in one pass. 501 today, so this is headroom, not a
#: fence — but an unbounded selector on a beat is how a pass becomes the thing
#: that starves the queue it runs on.
_LINKED_POLY_MAX_MARKETS = 600

#: Wall-clock budget, mirroring `_refresh_linked_game_books`.
_LINKED_POLY_DEADLINE_S = 240.0

#: "This event is on now or soon": live, or scheduled inside the horizon (with
#: the lookback for a row that has kicked off and not yet flipped). One string,
#: shared with #837's head arm of the sunk-recovery pass, so the two passes can
#: never disagree about which games are imminent. Needs `e` bound to `events`.
_LINKED_POLY_EVENT_WINDOW = """(
             e.status = 'live'
          OR (
                e.status = 'scheduled'
                AND e.commence_time > NOW() - make_interval(hours => :lookback_hours)
                AND e.commence_time <= NOW() + make_interval(days => :horizon_days)
             )
           )"""

_LINKED_POLY_BOOKS_SQL = text(
    """
    SELECT fm.id,
           fm.external_id,
           fm.name,
           fm.event_id,
           fm.category,
           fm.market_tier,
           -- #2027: carried, not filtered on. The pass still reaches a market
           -- whose resolution is behind us (its event can still read `live`);
           -- what it may not do is stamp that capture as the OPENING line.
           fm.resolution_date
      FROM futures_markets fm
      JOIN events e ON e.id = fm.event_id
     WHERE fm.source = 'polymarket'
       AND fm.status = 'open'
       -- The Gamma EVENT id is what `/events?id=` addresses. A row keyed by a
       -- bare condition_id is a decomposed SUB-market and is not fetchable this
       -- way; it is also never the row a dark event is missing (all 501 measured
       -- rows are parents), so excluding it costs nothing and keeps every id in
       -- the batch answerable.
       AND fm.external_id NOT LIKE '0x%'
       AND """
    + _LINKED_POLY_EVENT_WINDOW
    + """
       AND NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id
           )
     ORDER BY e.commence_time
     LIMIT :max_markets
    """
)


#: The repo's OWN definition of a single-game matchup name, character for
#: character: `app/routes/events.py::_GAME_MATCHUP_RE`, the regex
#: `_build_related_futures` uses to decide whether a market is tied to one game.
#: Copied rather than imported because a task importing a route module at call
#: time is an import cycle waiting to happen, and pinned equal by
#: `test_the_predicate_is_the_routes_own_definition` so the two cannot drift:
#: the label this pass writes and the route's own game-specific test have to
#: mean the same thing or the page disagrees with the database about what a row
#: is.
#:
#: NOT a matcher helper. `prediction_market_matching`'s matchup extractors are
#: PERMISSIVE by design — a false accept there costs a candidate that later
#: checks reject. This drives a DISPLAY label, where a false accept is a wrong
#: label on a page with nothing downstream to catch it. The route's regex is the
#: display-side definition and refuses the prose that trips a permissive one:
#: "Who will be UFC Middleweight champion at the end of 2026?" contains the word
#: "at" and is correctly rejected.
_GAME_MATCHUP_NAME_RE = re.compile(
    r"\bvs\.?\s|\s–\s|\bat\b.*:\s*\w|^[\w][\w\s.'\-()]+\bat\b\s+[\w][\w\s.'\-()]+$",
    re.IGNORECASE,
)


def _is_one_game_matchup_name(name: str | None) -> bool:
    """Does this market name describe ONE contest between two named sides?"""
    return bool(name) and bool(_GAME_MATCHUP_NAME_RE.search(name))


async def _refresh_linked_polymarket_books(deadline_s: float | None = None) -> dict:
    """Give a price to a LINKED Polymarket market that has no outcome rows at all.

    ## the hole this fills

    Exactly #3518's hole, one venue over. A market row is created by the hourly
    discovery poll on FIRST sight, and its outcome rows are written in the same
    pass — but only for the sub-markets that carry a price *at that moment*. A
    fight listed before its book opens gets a parent row and nothing else, and
    then nothing ever comes back for it:

    * ``_poll_polymarket_markets`` is a bounded, newest-first discovery scan.
      Measured 2026-09-06 over the 1,607 open Polymarket markets linked to a
      live-or-future event, by ``volume_updated_at`` (written only by that
      poll's own upsert): **152 touched inside six hours, 1,120 not for over a
      day, 279 not for over a week.**
    * ``futures_price_refresh`` (#2199) addresses markets by id and could reach
      them — and states in its own docstring that it "deliberately does NOT
      create markets, **create outcomes**". A price for an outcome row we do not
      hold is counted and dropped, by design.
    * ``_poll_live_prediction_market_prices`` is UPDATE-only.

    Every path needs an outcome row to exist, and the one path that creates them
    cannot reach the market again. **501 open linked markets across 159 events**
    were dark on 2026-09-06; **20 of those event pages showed no price from any
    source at all** — the reader-facing end of it is a page reading "No price
    yet" while Polymarket quotes the fight. The specimen: event 15305793, UFC 331
    Ozzy Diaz vs Ryan Gandra, our market ``972409`` with zero outcome rows
    against a venue book of 21c bid / 38c ask.

    ## what it does, and the four things it refuses

    Batched ``/events?id=`` reads (the addressing #2199 built), parsed through the
    service, priced by :func:`_parent_outcome_data` — the poll's own function, so
    a dark market gets the price the poll would have given it and never a second
    opinion.

    * **It never invents a price.** Nothing here decides what a book is worth;
      every refusal (placeholder slots, the #151 evidence gate, the #1578
      phantom-midpoint test) is inherited whole from that shared function, and a
      market it prices at nothing simply gets no row.
    * **It never overwrites anything.** Every write is
      ``ON CONFLICT DO NOTHING`` on a market SELECTED for having no outcome rows.
      A row that appears underneath us — a poll landing mid-pass — wins. There is
      no update branch to get a grade guard wrong (gotcha #21): a graded row
      cannot be in this population, because a graded row is a row.
    * **It never touches identity.** No ``event_id``, no ``commence_time``, no
      tier, no name on the market row. Two writers on one column is #3532's whole
      story and this pass is not the second one. The ONE market-row column it
      does write is ``category``, a display label, and only on a row it has just
      given its first legs — see the block that does it for why a price nobody
      can see is not a ship, and for the population it deliberately leaves alone.
    * **It refuses an incoherent field.** CAL-P006 (#1527), the same guard and
      the same reason as the poll: an impossible field is not a price.

    ``opening_probability`` is written only under the poll's own
    ``has_real_trading`` test AND its own hindsight refusal
    (:func:`opening_capture_is_hindsight`, #2027), so a first sighting through
    this path cannot bank an opening the poll would have declined to bank.
    That sentence is the whole reason the second gate is here: this pass
    CREATES first legs, which is precisely the population #2027 measured, and
    a claim of inheritance that the code does not implement is worse than no
    claim at all.
    """
    import asyncio
    import time as _time

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.odds_math import probability_to_american

    started = _time.monotonic()
    # One capture time for the whole pass, as every other snapshot writer does.
    now = datetime.now(timezone.utc)
    budget = _LINKED_POLY_DEADLINE_S if deadline_s is None else deadline_s

    stats: dict = {
        "markets_selected": 0,
        "batches_read": 0,
        "batches_unreadable": 0,
        "markets_reached": 0,
        "markets_absent_at_venue": 0,
        "markets_unpriced_at_venue": 0,
        "incoherent_fields_skipped": 0,
        # #2027: present at zero, always. "We stopped minting hindsight
        # openings" has to be a number somebody can read, and a key that only
        # appears when it fires cannot tell a quiet pass from a blind one.
        "opening_refused_hindsight": 0,
        "outcomes_created": 0,
        "snapshots_written": 0,
        "display_labels_corrected": 0,
        "deadline_hit": False,
        "errors": [],
    }

    async with get_task_session() as session:
        rows = (
            await session.execute(
                _LINKED_POLY_BOOKS_SQL,
                {
                    "lookback_hours": LINKED_POLY_BOOK_LOOKBACK_HOURS,
                    "horizon_days": LINKED_POLY_BOOK_HORIZON_DAYS,
                    "max_markets": _LINKED_POLY_MAX_MARKETS,
                },
            )
        ).fetchall()

        stats["markets_selected"] = len(rows)
        if not rows:
            # Gotcha #53: an empty result is a SHAPE. "Nothing is dark" and "the
            # selector is broken" produce the same empty list, so the terminal
            # says which question was asked.
            stats["terminal"] = "no_dark_linked_markets_in_window"
            return stats

        # Copy to plain scalars: the per-market commit below expires ORM state,
        # and a row read after it is a row that may not answer (gotcha #6).
        work = [
            {
                "id": r.id,
                "external_id": str(r.external_id),
                "name": r.name,
                "category": r.category,
                "market_tier": r.market_tier,
                "resolution_date": r.resolution_date,
            }
            for r in rows
        ]
        by_external_id = {w["external_id"]: w for w in work}

        service = PolymarketAPIService()
        try:
            ids = list(by_external_id.keys())
            for start in range(0, len(ids), _LINKED_POLY_ID_BATCH):
                if _time.monotonic() - started > budget:
                    stats["deadline_hit"] = True
                    break

                chunk = ids[start : start + _LINKED_POLY_ID_BATCH]
                try:
                    raw_events = await service.get_events_by_ids(chunk)
                except Exception as exc:  # noqa: BLE001 — one batch may not end the run
                    stats["batches_unreadable"] += 1
                    stats["errors"].append(f"batch {chunk[0]}…: {str(exc)[:120]}")
                    continue
                stats["batches_read"] += 1

                # Key by the event's OWN id, never by request order: Gamma omits
                # ids it does not recognise, so the response neither lines up with
                # the request nor promises its length (that function says so).
                parsed = {}
                for raw in raw_events:
                    event = service._parse_event(raw)
                    if event and event.id:
                        parsed[str(event.id)] = event

                for external_id in chunk:
                    row = by_external_id[external_id]
                    event = parsed.get(external_id)
                    if event is None:
                        # Recorded, never acted on: a market row is not retired on
                        # the strength of one absent read (gotcha #53).
                        stats["markets_absent_at_venue"] += 1
                        continue
                    stats["markets_reached"] += 1

                    outcome_data = _parent_outcome_data(event)
                    if not outcome_data:
                        stats["markets_unpriced_at_venue"] += 1
                        continue

                    # CAL-P006 (#1527), the poll's guard, same reason: a negRisk
                    # field with several near-certain legs is not a price.
                    if field_is_incoherent(
                        (od["prob"] for od in outcome_data),
                        mutually_exclusive=bool(event.neg_risk),
                    ):
                        stats["incoherent_fields_skipped"] += 1
                        logger.warning(
                            "Polymarket event %s (%s): %d/%d legs near-certain on "
                            "a negRisk single-winner field — refusing to capture "
                            "(#1527)",
                            event.id, (event.title or "")[:80],
                            count_near_certain(od["prob"] for od in outcome_data),
                            len(outcome_data),
                        )
                        continue

                    outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                    # Whether THIS market got a leg, not whether the pass did:
                    # the label correction below must not fire on a market whose
                    # every leg lost the `ON CONFLICT DO NOTHING` race.
                    _created_before_this_market = stats["outcomes_created"]

                    # #2027: the poll's hindsight refusal, inherited whole.
                    #
                    # CERT-3202 moved it INSIDE the loop and this comment used
                    # to be the error: it said the refusal was "a property of
                    # the market and its capture time — not of a leg", and
                    # passed `market=None`. It is a property of a leg. A
                    # Polymarket event stays open while its children settle one
                    # by one, so an event-wide decision either refuses a whole
                    # live field or — the case that shipped — banks a settled
                    # child's book as an opening because its parent was open.
                    # `resolution_date` is still that market's own stored date
                    # (the parent event.end_date the poll wrote), and the event
                    # and date arms are unchanged; only the per-child arm is new.
                    _resolution_date = row.get("resolution_date")

                    for rank, od in enumerate(outcome_data, 1):
                        prob = od["prob"]
                        american = (
                            probability_to_american(prob) if 0 < prob < 1 else None
                        )
                        # The poll's own test, not a new one.
                        has_real_trading = (
                            od["yes_bid"] is not None
                            and od["yes_bid"] > 0
                            and od["yes_ask"] is not None
                            and (od["yes_ask"] - od["yes_bid"]) < 0.50
                        ) or (
                            od.get("last_price") is not None and od["last_price"] > 0
                        )
                        if has_real_trading and opening_capture_is_hindsight(
                            event, od.get("market"), _resolution_date, now
                        ):
                            stats["opening_refused_hindsight"] = (
                                stats.get("opening_refused_hindsight", 0) + 1
                            )
                            has_real_trading = False

                        created_id = (
                            await session.execute(
                                pg_insert(FuturesOutcome)
                                .values(
                                    market_id=row["id"],
                                    external_id=od["external_id"],
                                    name=od["name"],
                                    current_probability=prob,
                                    current_american_odds=american,
                                    current_yes_bid=od["yes_bid"],
                                    current_yes_ask=od["yes_ask"],
                                    opening_probability=prob if has_real_trading else None,
                                    opening_american_odds=(
                                        american if has_real_trading else None
                                    ),
                                    opening_captured_at=now if has_real_trading else None,
                                    rank=rank,
                                    # Explicit, and load-bearing: the column is
                                    # `boolean NULL DEFAULT false`, so an INSERT
                                    # that omits it stores an affirmative graded
                                    # LOSS (CAL-P1004R) on a leg nobody called.
                                    is_winner=None,
                                    resolution_source=None,
                                )
                                .on_conflict_do_nothing(
                                    index_elements=["market_id", "external_id"]
                                )
                                .returning(FuturesOutcome.id)
                            )
                        ).scalar()

                        if created_id is None:
                            # DO NOTHING fired: a concurrent writer got there
                            # first and its row, not ours, is the truth.
                            continue
                        stats["outcomes_created"] += 1

                        await session.execute(
                            pg_insert(FuturesOddsSnapshot).values(
                                outcome_id=created_id,
                                bookmaker="polymarket",
                                probability=prob,
                                american_odds=american,
                                yes_bid=od["yes_bid"],
                                yes_ask=od["yes_ask"],
                                last_price=od["last_price"],
                                captured_at=now,
                            )
                        )
                        stats["snapshots_written"] += 1

                    # ── The half that makes the price READABLE (CERT-2111) ──
                    #
                    # A price nobody can see is not a ship. CERT-2111 measured
                    # the rest of the path: the leg written above does reach
                    # `/related-futures`, and the web `categorizeFutures()`
                    # (`components/RelatedFutures.tsx`) then DROPS it — it has
                    # buckets for `game_prop`, `award`, `season_stat`,
                    # `playoff_path`, `conference`, `series`, `trade`,
                    # `novelty` and `other`, and none at all for
                    # `championship`. `display_category` is
                    # `classify_market_category(...)`, which for a name like
                    # this one returns the market's own `category` verbatim.
                    #
                    # So the row is invisible because a Polymarket game
                    # moneyline was born labelled `championship`. The working
                    # sibling proves what the right label is rather than my
                    # guessing it: event 15190803, the same UFC card, renders
                    # under Bigger Picture -> GAME PROPS from market 60285732,
                    # whose `category` is `game_prop`; its parent row 60280233
                    # carries `championship` and is dropped exactly like ours.
                    #
                    # This is a DISPLAY label, not identity — no `event_id`, no
                    # `commence_time`, no tier, no name, no price — and it is
                    # written ONLY on a row this pass has just given its first
                    # legs, that is linked to an event (the selector's own
                    # requirement), is tier 5, and whose name describes one
                    # contest between two sides. `IS DISTINCT FROM` keeps it a
                    # no-op on a row already labelled correctly.
                    #
                    # DELIBERATELY NOT WIDENED. The same mislabel sits on
                    # **7,167 open tier-5 event-linked matchup markets**
                    # (6,666 Polymarket + 501 Kalshi, production 2026-09-06),
                    # every one of them invisible in Bigger Picture. Relabelling
                    # that population is a product decision about what an event
                    # page shows, not a rider on a price-capture fix; it is
                    # filed as #3649 for the surface's owner.
                    if (
                        stats["outcomes_created"] > _created_before_this_market
                        and (row.get("category") or "") != "game_prop"
                        and row.get("market_tier") == 5
                        and _is_one_game_matchup_name(row.get("name"))
                    ):
                        await session.execute(
                            text(
                                "UPDATE futures_markets SET category = 'game_prop' "
                                "WHERE id = :id "
                                "AND category IS DISTINCT FROM 'game_prop'"
                            ),
                            {"id": row["id"]},
                        )
                        stats["display_labels_corrected"] += 1

                    # #6598: same rule as the main poll. This pass INSERTs legs
                    # with `on_conflict_do_nothing`, so a market that already
                    # held legs now carries two numberings — the batch's 1..N
                    # beside whatever its existing rows were last given. Only
                    # worth a statement when this market actually gained legs.
                    if stats["outcomes_created"] > _created_before_this_market:
                        await session.execute(
                            rerank_market_field_stmt(row["id"])
                        )

                    # Per-market commit: one bad market may not roll back a whole
                    # batch's worth of prices (gotcha #13 / #42).
                    try:
                        await session.commit()
                    except Exception as exc:  # noqa: BLE001
                        await session.rollback()
                        stats["errors"].append(f"{external_id}: {str(exc)[:120]}")

                await asyncio.sleep(0.2)
        finally:
            await service.close()

    stats["elapsed_s"] = round(_time.monotonic() - started, 1)
    stats["terminal"] = "deadline" if stats["deadline_hit"] else "complete"
    return stats


# =========================================================================
# Sunk open events (#6758) — the poll's writer, re-aimed at rows it can no
# longer reach
# =========================================================================
#
# `_poll_polymarket_markets` reads the newest 2,000 open events by `startDate`
# (Gamma's offset cap). Measured 2026-09-17 16:39Z on Discover's saved pages:
# offset 0 is 16:33Z and offset 1900 is 05:35Z — the whole window is ~10.5 hours
# deep and 86-91% of it is five-minute crypto candles the writer discards. So an
# open event gets roughly ten hourly visits after it is listed and then none.
#
# That would be harmless if everything were written on first sight. It is not,
# and correctly so: a child whose book is empty is REFUSED (#151/#1578/#6676 —
# "it is re-captured next cycle once a real bid/trade appears"). For a fight
# listed two weeks out, the book opens long after the last cycle that can see
# it. Event 1013438 (Dumont–Perez, listed 09-12, fights 09-26): parent row
# 60880026 held since 09-12 with 0 legs and 0 of 19 children.
#
# `_refresh_linked_polymarket_books` (#3613) is the same idea and cannot cover
# this: it needs an `events` link (these cards have none), it needs ZERO outcome
# rows (a parent holding one prop is excluded for good), and it writes parent
# legs only — never the child market rows a bout page is made of.
#
# This pass adds no pricing and no writer. It selects open parents the poll has
# stopped touching (`volume_updated_at`, the poll's own stamp), re-reads them by
# id (`/events?id=`, not subject to the offset cap) and hands the parsed events
# to `_process_event_batch` — the poll's own function. A recovered event is
# written exactly as if the poll had reached it, every refusal included.

#: Six missed hourly polls. The window was ~10.5h deep when measured; a row the
#: poll has not stamped for six hours has left it or is about to.
SUNK_POLY_STALE_HOURS = 6

#: Rows resolving inside this horizon are read every pass, soonest first.
#: #3613's measured figure, reused rather than re-chosen.
SUNK_POLY_IMMINENT_DAYS = LINKED_POLY_BOOK_HORIZON_DAYS

#: Per-pass ceilings. 600 events = 30 Gamma calls, the same ceiling as #3613,
#: plus the #837 head arm's 100 (5 calls) on top rather than carved out of the
#: imminent arm, which still owns every sunk row with no event link — the
#: fight cards #6758 was written for. 100 is the head's measured reach: on
#: 2026-09-23 23:40Z the window held 2,942 linked sunk parents, 99 of them
#: starting inside two days, so one pass covers the next two days of games.
_SUNK_POLY_HEAD_MAX = 100
_SUNK_POLY_IMMINENT_MAX = 300
_SUNK_POLY_ROTATE_MAX = 300
_SUNK_POLY_DEADLINE_S = 240.0

_SUNK_POLY_CURSOR_KEY = "bainluck:polymarket_sunk_recovery:cursor"
#: Ids the venue would not give us an OPEN event for. Without this they would be
#: re-selected every pass (nothing stamps them) and hold the imminent head — the
#: #2222 failure. Expires with the staleness window, so each is retried.
_SUNK_POLY_REFUSED_KEY = "bainluck:polymarket_sunk_recovery:refused"

def _sunk_poly_where(stale_param: str = "stale_hours") -> str:
    """The sunk predicate, with the STALENESS test bound to ``stale_param``.

    #7930: the post-start arm needs a shorter staleness than the other arms but
    the same resolution floor, so the two are bound separately. The default
    renders the predicate every other arm has always used, byte for byte.
    """
    return """
      FROM futures_markets fm
     WHERE fm.source = 'polymarket'
       AND fm.status = 'open'
       -- Parents only: `/events?id=` addresses the Gamma EVENT id. Children are
       -- reached through their parent, which is how the poll reaches them.
       AND fm.external_id NOT LIKE '0x%'
       AND (fm.volume_updated_at IS NULL
            OR fm.volume_updated_at < NOW() - make_interval(hours => :""" + stale_param + """))
       -- A floor as well as an order (gotcha #41): never spend the pass on rows
       -- whose resolution is already behind us — settlement owns those.
       AND (fm.resolution_date IS NULL
            OR fm.resolution_date > NOW() - make_interval(hours => :stale_hours))
       AND NOT (fm.external_id = ANY(:refused))
"""


_SUNK_POLY_WHERE = _sunk_poly_where()

_SUNK_POLY_IMMINENT_SQL = text(
    "SELECT fm.id, fm.external_id"
    + _SUNK_POLY_WHERE
    + """
       AND fm.resolution_date <= NOW() + make_interval(days => :horizon_days)
     ORDER BY fm.resolution_date, fm.id
     LIMIT :max_rows
    """
)

#: #837/#5273: the HEAD arm — sunk parents whose linked game is live or about to
#: start, soonest kick-off first, read before either arm below.
#:
#: The imminent arm orders by `resolution_date`, which for a Polymarket game is
#: Gamma's `endDate` — a week after first pitch for MLB. Measured 2026-09-23
#: 23:30Z: Blue Jays–Orioles (parent 61294015, Gamma 1038120, event 15317724)
#: resolved 09-30 and sat behind 3,515 of 6,324 stale imminent rows, at 300 a
#: pass. Its moneyline child had never been minted (the book was empty on the
#: listing day, and the empty-book refusal is correct), so the game played with
#: no winner price, and the pass reached it a week after the final.
#:
#: The window is #3613's own predicate (`_LINKED_POLY_EVENT_WINDOW`) WITHOUT its
#: zero-outcomes clause: this parent already holds its own raw legs, and what is
#: missing is its children, which only the poll's writer mints. Everything else
#: is `_SUNK_POLY_WHERE` unchanged — stale, open, floored, refusals honoured — so
#: a row the poll still stamps hourly is never re-read, and one this arm writes
#: leaves the arm for six hours like any other.
_SUNK_POLY_HEAD_SQL = text(
    "SELECT s.id, s.external_id FROM (SELECT fm.id, fm.external_id, fm.event_id"
    + _SUNK_POLY_WHERE
    + """
    ) s
      JOIN events e ON e.id = s.event_id
     WHERE """
    + _LINKED_POLY_EVENT_WINDOW
    + """
     ORDER BY e.commence_time, s.id
     LIMIT :max_rows
    """
)

#: #8373: the venue's own fixture instant, or NULL. Guarded rather than cast
#: bare so one malformed stamp cannot fail the whole pass (all 22,134 open
#: stamps matched this shape on 2026-09-24; `[:]` keeps text() from reading a
#: bind parameter, gotcha #45).
_SUNK_POLY_VENUE_START = """(CASE WHEN fm.market_metadata->>'venue_game_start'
              ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}[:][0-9]{2}[:][0-9]{2}([.][0-9]+)?([+-][0-9]{2}[:][0-9]{2}|Z)?$'
         THEN (fm.market_metadata->>'venue_game_start')::timestamptz END)"""

#: #8373: the UNLINKED game arm — sunk parents with no `events` link whose own
#: `venue_game_start` sits inside the linked window, soonest first, read right
#: after the head arm.
#:
#: The head arm joins `events`, so it cannot see a game parent the matcher has
#: not linked, and a MOVED game is exactly that. Polymarket 1058697 (slug
#: `mlb-chc-bos-2026-09-27`) was moved to Cubs–Red Sox doubleheader game 1 on
#: 09-25 17:05Z; our parent still held the pre-move `venue_game_start`
#: 09-27T19:05Z, so the matcher could not link it, and with no link it fell to
#: the imminent arm, ordered by `resolution_date` (10-04) behind thousands. Its
#: last write was its listing day (09-21 20:15Z), so the game-1 page read
#: "No price yet" while the venue priced it. Only a re-read rewrites the stamp;
#: this arm is what makes the re-read arrive before first pitch.
#:
#: Ordered by the STORED start, which is stale for a moved game but is still
#: the only fixture date we hold. Measured 2026-09-24 13:55Z: 1,275 rows in the
#: window, the specimen's stale 09-27 behind 663 of them. A row read leaves the
#: arm for `SUNK_POLY_STALE_HOURS`, so 200 a pass (10 Gamma calls, hourly) reads
#: the soonest ~1,200 once per staleness window — the specimen on the fourth
#: pass. Everything else is `_SUNK_POLY_WHERE` unchanged.
_SUNK_POLY_UNLINKED_GAME_SQL = text(
    "SELECT s.id, s.external_id FROM (SELECT fm.id, fm.external_id, "
    + _SUNK_POLY_VENUE_START
    + " AS venue_start"
    + _SUNK_POLY_WHERE
    + """
       AND fm.event_id IS NULL
    ) s
     WHERE s.venue_start > NOW() - make_interval(hours => :lookback_hours)
       AND s.venue_start <= NOW() + make_interval(days => :horizon_days)
     ORDER BY s.venue_start, s.id
     LIMIT :max_rows
    """
)
_SUNK_POLY_UNLINKED_GAME_MAX = 200

#: #7930: the POST-START arm — game parents whose own `venue_game_start` is
#: behind us (inside two days), linked or not, oldest start first.
#:
#: The two six-hour windows above cancel out after first pitch. The poll last
#: stamps a game parent 0–2h before the start; `SUNK_POLY_STALE_HOURS` then
#: holds it out until about start+6h, which is exactly when the unlinked arm's
#: six-hour lookback closes behind it (and the head arm lets go the moment the
#: event leaves live/scheduled). What is left is the imminent arm, ordered by
#: `resolution_date` — start+7d for a Polymarket game — behind a pool that sits
#: at its 300 limit. So a finished game's props stay `open` on our side for
#: days after the venue closed them. Measured on the venue 2026-09-25: 19 of 24
#: sampled post-start parents read `closed=true` (6/8 at 4–8h, 6/8 at 8–16h,
#: 7/8 at 16–36h), from 402 open post-start rows in the last day and 430 in
#: the day before.
#:
#: The writer is already right once a row is reached: a closed event goes to
#: `_process_event_batch`, which stamps `status='resolved'` (see #7930 above).
#: This arm only makes the re-read arrive. Staleness is one hour, not six,
#: because the question after the start is "has it closed yet", which changes
#: by the hour; the resolution floor is the shared one. Oldest start first
#: inside a 48h floor (gotcha #41) — the longest-finished games are the ones
#: most surely closed at the venue. 200 a pass = 10 Gamma calls.
SUNK_POLY_POST_START_STALE_HOURS = 1
SUNK_POLY_POST_START_LOOKBACK_HOURS = 48
_SUNK_POLY_POST_START_MAX = 200

_SUNK_POLY_POST_START_SQL = text(
    "SELECT s.id, s.external_id FROM (SELECT fm.id, fm.external_id, "
    + _SUNK_POLY_VENUE_START
    + " AS venue_start"
    + _sunk_poly_where("post_start_stale_hours")
    + """
    ) s
     WHERE s.venue_start > NOW() - make_interval(hours => :post_start_lookback_hours)
       AND s.venue_start <= NOW()
     ORDER BY s.venue_start, s.id
     LIMIT :max_rows
    """
)

#: Everything else — politics, entertainment, economics, season-long futures —
#: by id behind a cursor, so a far-dated row is reached in a bounded number of
#: passes however large the imminent arm is. Same shape as the status sync.
_SUNK_POLY_ROTATE_SQL = text(
    "SELECT fm.id, fm.external_id"
    + _SUNK_POLY_WHERE
    + """
       AND (fm.resolution_date IS NULL
            OR fm.resolution_date > NOW() + make_interval(days => :horizon_days))
       AND fm.id > :cursor
     ORDER BY fm.id
     LIMIT :max_rows
    """
)


def sunk_event_is_open(event) -> bool:
    """Whether a re-read event may go to the poll's writer. Pure.

    The poll gets this for free from `closed=false` on the list request; an
    id-addressed read has no such filter, and the writer stamps
    `status='open' if event.active` — Gamma keeps `active=true` on a CLOSED
    event, so without this a settled fight would be re-opened and re-priced.
    """
    return bool(
        getattr(event, "active", False)
        and not getattr(event, "closed", False)
        and not getattr(event, "archived", False)
    )


def sunk_event_child_census(event) -> tuple[int, int]:
    """`(children at the venue, children the writer would price)`. Pure.

    Exists so the pass can never report a half-written event as recovered: the
    second number comes from the writer's own resolver, not a second opinion.
    """
    markets = list(getattr(event, "markets", None) or [])
    priced = sum(1 for m in markets if (_resolve_market_probability(m) or 0) > 0)
    return len(markets), priced


# ── #7930: the venue stopped offering the question and we kept serving it ────
#
# `/events?id=` IS A LIST ENDPOINT AND IT HIDES ARCHIVED EVENTS. That single
# fact is the whole defect. The batch read above cannot distinguish
#
#     (a) "Gamma has no such event"                      — a genuine absence
#     (b) "Gamma has it and has stopped offering it"     — archived, the case
#     (c) "the page was short / the id fell out"         — a read artifact
#
# because all three arrive as the same thing: an id missing from a 200. That is
# gotcha #53 at the batch boundary, and the code above answered it the only way
# it could — record, refuse, act on nothing.
#
# MEASURED ON THE VENUE, 2026-09-22 06:05Z (notice 26 — the venue's own API, by
# direct address, not our mirror). 240 rows drawn from `_SUNK_POLY_WHERE`'s OWN
# predicate, sampled BOTH ways so ordering could not fake the answer:
#
#     oldest-id first   120   71 offered   49 NOT OFFERED   0 absent (404)
#     newest-id first   120   31 offered   88 NOT OFFERED   0 absent (404)   1 transport error
#
# **137 of 240 (57%) are off the board, and not one of the 240 was a 404.** So
# the rows #7930's body called "absent from the venue" are not absent at all:
# the venue still holds every one and has taken them off the board. The four
# Brazil rows the issue named (871036/871037/871038/871045) read
# `archived=true, active=false` on `/events/{id}` and `200 []` on
# `/events?id=` — that contrast is the whole defect, and it is why the issue's
# own shape A and shape B are ONE shape with two flag spellings.
#
# The bulk of the 137 are finished fixtures — European T20, KBO, CPBL, `Who
# will Petr Yan fight next?` — sitting in our rows as live questions.
#
# REACH: the selector holds 9,531 rows today, so on this rate the pass has on
# the order of 5,000 rows to settle, at ~600 ids/hour. Every one of those writes
# moves in a single direction — a market the venue closed stops being served as
# open — and the writer's branch is strictly tightening (it adds ways to be
# `resolved` and removes none), so no row can be pushed ONTO a surface by this.
#
# THE DIRECT-ADDRESS READ IS A DIFFERENT QUESTION, NOT A RETRY. `/events/{id}`
# answers 404 for an id Gamma does not have (verified against 999999999) and 200
# with the full flag set for an archived one. So it separates (a) from (b) and
# (c) POSITIVELY — the decision stops resting on an absence and starts resting on
# a flag the venue published. `get_event_by_id` is the right client method for
# it and the only one: it returns None for 404 ONLY and re-raises 429/5xx/timeout
# (gotcha #36), which is exactly the distinction this arm is made of.
#
# AND THERE IS NO NEW WITHDRAWAL MECHANISM HERE, BECAUSE THE WRITER ALREADY HAS
# ONE. `_process_event_batch` computes `_venue_open = sunk_event_is_open(event)`
# and upserts `status="open" if _venue_open else "resolved"` with the `settled_at`
# stamp in the same statement. It is already fed `closed=True` events by the
# settled-sports tag sweep, so this is an established input shape and not a new
# one. The recovery pass was DETECTING the case (`events_closed_at_venue`) and
# then throwing the event away one line later — the row never reached the writer
# that knew what to do with it. Sending it is the fix; inventing a second
# vocabulary for "withdrawn" would have been a second copy of that rule.

#: Ceiling on direct-address reads per pass. The batch read is 1 call per 20 ids
#: and this arm is 1 call per id, so it is the expensive half and gets an
#: explicit budget rather than the pass deadline as its only bound. 60 = three
#: batches' worth of misses, comfortably above the miss rate a healthy pass sees
#: and low enough that a Gamma-wide outage (every id missing) cannot turn one
#: pass into 600 sequential requests.
_SUNK_POLY_DIRECT_MAX = 60

#: Pause between direct-address reads. The batch arm sleeps 0.3 s between its
#: 20-id calls; this arm can issue 60 single-id calls in a row, so it takes the
#: same courtesy at a third of the size. At the ceiling that is 6 s of a 240 s
#: budget — cheap enough to be worth not being the caller Gamma rate-limits.
_SUNK_POLY_DIRECT_PAUSE_S = 0.1


def sunk_direct_verdict(found: bool, event) -> str:
    """What a DIRECT-ADDRESS `/events/{id}` read says about one event. Pure.

    ``found`` is ``get_event_by_id(...) is not None`` — False means Gamma
    answered 404, and it answers 404 for nothing else (gotcha #36; the method's
    own contract). ``event`` is the service's parse of that body, or None if it
    would not parse. Transport failures never reach here: ``get_event_by_id``
    re-raises them and the caller counts them without concluding anything, which
    is the fail-closed half of this arm.

    Four verdicts, and they are four different facts — never three plus a
    default, because the two that must write nothing are the two a default would
    swallow:

    * ``"absent"``      — Gamma does not have this event (404). Recorded, acted
      on by nothing: one channel's absence is not a fact about the market
      (gotcha #53), and 0 of 240 sampled rows were this.
    * ``"not_offered"`` — Gamma HAS it and :func:`sunk_event_is_open` says it is
      off the board. The venue's own published flags, not an inference from
      silence. This is the one the ship acts on.
    * ``"offered"``     — the list read simply missed it; a normal recovery.
    * ``"unparseable"`` — a 200 whose body is not an event we understand.
      Concludes nothing, same as a transport error.
    """
    if not found:
        return "absent"
    if event is None or not getattr(event, "id", None):
        return "unparseable"
    return "offered" if sunk_event_is_open(event) else "not_offered"


async def _recover_sunk_polymarket_events(deadline_s: float | None = None) -> dict:
    """#6758: re-read open Polymarket parents the discovery poll no longer reaches."""
    import asyncio
    import time as _time

    import httpx
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.redis_state import get_redis_client
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    started = _time.monotonic()
    budget = _SUNK_POLY_DEADLINE_S if deadline_s is None else deadline_s

    stats: dict = {
        "head_selected": 0,
        "unlinked_game_selected": 0,  # #8373
        "post_start_selected": 0,  # #7930
        "head_pool_at_limit": False,
        "imminent_selected": 0,
        "rotate_selected": 0,
        "imminent_pool_at_limit": False,
        "batches_read": 0,
        "batches_unreadable": 0,
        "events_reached": 0,
        # #7930: three counts where there was one, because they were three
        # different facts sharing a name. `events_absent_at_venue` used to mean
        # "the LIST read did not return this id" and now means what it says —
        # the direct-address channel answered 404. `events_missing_from_list` is
        # the old number under an honest name, and is a question rather than a
        # finding; `events_recovered_by_direct` is the part of it the list was
        # simply wrong about.
        "events_missing_from_list": 0,
        "events_absent_at_venue": 0,
        "events_recovered_by_direct": 0,
        "direct_reads": 0,
        "direct_unreadable": 0,
        "direct_unparseable": 0,
        "direct_budget_hit": False,
        "events_closed_at_venue": 0,
        "events_fully_priced_at_venue": 0,
        "events_partially_priced_at_venue": 0,
        "events_unpriced_at_venue": 0,
        "children_at_venue": 0,
        "children_priced_at_venue": 0,
        "deadline_hit": False,
        "rate_limited": False,
        "errors": [],
        # What the poll's writer counts, under the poll's own key names.
        "writer": {
            "events_processed": 0, "markets_processed": 0, "outcomes_updated": 0,
            "snapshots_created": 0, "legs_retired": 0, "errors": [],
            "by_category": {}, "crypto_skipped": 0,
        },
    }

    # Redis is an optimisation here, never a precondition: with no cursor the
    # rotate arm restarts at 0, with no refused-set nothing is excluded, and the
    # LIMITs bound the pass either way.
    rc = None
    cursor = 0
    refused: list[str] = []
    try:
        rc = get_redis_client()
        cursor = int(rc.get(_SUNK_POLY_CURSOR_KEY) or 0)
        raw = rc.smembers(_SUNK_POLY_REFUSED_KEY) or ()
        refused = sorted(m.decode() if isinstance(m, bytes) else str(m) for m in raw)
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"redis read: {str(exc)[:80]}")
        rc, cursor, refused = None, 0, []

    base = {
        "stale_hours": SUNK_POLY_STALE_HOURS,
        "horizon_days": SUNK_POLY_IMMINENT_DAYS,
        "refused": refused,
    }
    # #837: the head arm reads the linked-game window, which is #3613's.
    head_params = {
        **base,
        "horizon_days": LINKED_POLY_BOOK_HORIZON_DAYS,
        "lookback_hours": LINKED_POLY_BOOK_LOOKBACK_HOURS,
        "max_rows": _SUNK_POLY_HEAD_MAX,
    }
    async with get_task_session() as session:
        imminent = (
            await session.execute(
                _SUNK_POLY_IMMINENT_SQL, {**base, "max_rows": _SUNK_POLY_IMMINENT_MAX}
            )
        ).fetchall()
        rotate = (
            await session.execute(
                _SUNK_POLY_ROTATE_SQL,
                {**base, "max_rows": _SUNK_POLY_ROTATE_MAX, "cursor": cursor},
            )
        ).fetchall()
        wrapped = False
        if not rotate and cursor:
            # Past the tail: the population shrank under the cursor. Wrap NOW
            # rather than spending a pass to discover it.
            wrapped = True
            cursor = 0
            rotate = (
                await session.execute(
                    _SUNK_POLY_ROTATE_SQL,
                    {**base, "max_rows": _SUNK_POLY_ROTATE_MAX, "cursor": 0},
                )
            ).fetchall()
        # #837: executed last so the two arms above keep their order, but its
        # ids go FIRST in the work list below — that ordering is the fix.
        head = (await session.execute(_SUNK_POLY_HEAD_SQL, head_params)).fetchall()
        # #8373: same window, keyed on the parent's own stored start.
        unlinked_game = (
            await session.execute(
                _SUNK_POLY_UNLINKED_GAME_SQL,
                {**head_params, "max_rows": _SUNK_POLY_UNLINKED_GAME_MAX},
            )
        ).fetchall()
        # #7930: after the start, keyed on the same stored start.
        post_start = (
            await session.execute(
                _SUNK_POLY_POST_START_SQL,
                {
                    **base,
                    "post_start_stale_hours": SUNK_POLY_POST_START_STALE_HOURS,
                    "post_start_lookback_hours": SUNK_POLY_POST_START_LOOKBACK_HOURS,
                    "max_rows": _SUNK_POLY_POST_START_MAX,
                },
            )
        ).fetchall()
        # Plain scalars before any commit (gotcha #6).
        head_ids = [str(r.external_id) for r in head]
        unlinked_game_ids = [str(r.external_id) for r in unlinked_game]
        post_start_ids = [str(r.external_id) for r in post_start]
        imminent_ids = [str(r.external_id) for r in imminent]
        rotate_pairs = [(int(r.id), str(r.external_id)) for r in rotate]

    stats["head_selected"] = len(head_ids)
    stats["unlinked_game_selected"] = len(unlinked_game_ids)
    stats["unlinked_game_pool_at_limit"] = (
        len(unlinked_game_ids) >= _SUNK_POLY_UNLINKED_GAME_MAX
    )
    stats["post_start_selected"] = len(post_start_ids)
    stats["post_start_pool_at_limit"] = len(post_start_ids) >= _SUNK_POLY_POST_START_MAX
    stats["head_pool_at_limit"] = len(head_ids) >= _SUNK_POLY_HEAD_MAX
    stats["imminent_selected"] = len(imminent_ids)
    stats["rotate_selected"] = len(rotate_pairs)
    stats["imminent_pool_at_limit"] = len(imminent_ids) >= _SUNK_POLY_IMMINENT_MAX
    stats["cursor_wrapped"] = wrapped

    if (
        not head_ids and not unlinked_game_ids and not post_start_ids
        and not imminent_ids and not rotate_pairs
    ):
        # Gotcha #53: say which question returned nothing.
        stats["terminal"] = "no_sunk_open_events"
        return stats

    # A head row can ALSO be a rotate row (no resolution date, or one past the
    # horizon). It is read in the head's chunk, so it must not advance the
    # rotate cursor from there: `max()` below would jump the cursor over every
    # rotate row between it and the last one actually read.
    # #8373: the same holds for an unlinked-game row, and (#7930) a post-start one.
    head_set = set(head_ids) | set(unlinked_game_ids) | set(post_start_ids)
    rotate_id_by_ext = {ext: mid for mid, ext in rotate_pairs if ext not in head_set}
    seen: set[str] = set()
    work: list[str] = []
    for ext in (
        head_ids + unlinked_game_ids + post_start_ids + imminent_ids
        + [ext for _mid, ext in rotate_pairs]
    ):
        if ext not in seen:  # one Gamma id, one write — never twice in a pass
            seen.add(ext)
            work.append(ext)

    newly_refused: list[str] = []
    direct_budget = _SUNK_POLY_DIRECT_MAX
    last_rotate_id_done = cursor
    service = PolymarketAPIService()
    try:
        for start in range(0, len(work), _LINKED_POLY_ID_BATCH):
            if _time.monotonic() - started > budget:
                stats["deadline_hit"] = True
                break
            if start:
                await asyncio.sleep(0.3)

            chunk = work[start : start + _LINKED_POLY_ID_BATCH]
            try:
                raw_events = await service.get_events_by_ids(chunk)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    # Stop, keep the cursor where it is, retry next pass.
                    stats["rate_limited"] = True
                    break
                stats["batches_unreadable"] += 1
                stats["errors"].append(f"batch {chunk[0]}…: HTTP {exc.response.status_code}")
                continue
            except Exception as exc:  # noqa: BLE001 — one batch may not end the run
                stats["batches_unreadable"] += 1
                stats["errors"].append(f"batch {chunk[0]}…: {str(exc)[:120]}")
                continue
            stats["batches_read"] += 1

            parsed = {}
            for raw in raw_events:
                event = service._parse_event(raw)
                if event and event.id:
                    parsed[str(event.id)] = event

            to_write = []
            missing = [ext for ext in chunk if ext not in parsed]
            stats["events_missing_from_list"] += len(missing)

            # #7930: the list read hides archived events, so a miss is a
            # QUESTION, not an answer. Ask the direct-address channel, which can
            # tell 404 from "we have it and took it off the board".
            for ext in missing:
                if direct_budget <= 0:
                    stats["direct_budget_hit"] = True
                    break
                if _time.monotonic() - started > budget:
                    stats["deadline_hit"] = True
                    break
                if stats["direct_reads"]:
                    await asyncio.sleep(_SUNK_POLY_DIRECT_PAUSE_S)
                direct_budget -= 1
                stats["direct_reads"] += 1
                try:
                    raw_one = await service.get_event_by_id(ext)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        # Same rule the batch arm follows: stop asking, keep the
                        # cursor, conclude nothing about the ids not yet read.
                        stats["rate_limited"] = True
                        direct_budget = 0
                        break
                    stats["direct_unreadable"] += 1
                    stats["errors"].append(f"direct {ext}: HTTP {exc.response.status_code}")
                    continue
                except Exception as exc:  # noqa: BLE001 — one id may not end the run
                    stats["direct_unreadable"] += 1
                    stats["errors"].append(f"direct {ext}: {str(exc)[:120]}")
                    continue

                one = service._parse_event(raw_one) if raw_one is not None else None
                verdict = sunk_direct_verdict(raw_one is not None, one)
                if verdict == "absent":
                    # Recorded, never acted on (gotcha #53): one absent read
                    # retires nothing. It is only kept out of the next passes.
                    stats["events_absent_at_venue"] += 1
                    newly_refused.append(ext)
                elif verdict == "unparseable":
                    # A 200 we cannot read is not a fact either. No refusal, so
                    # the next pass meets it again.
                    stats["direct_unparseable"] += 1
                else:
                    stats["events_recovered_by_direct"] += 1
                    parsed[ext] = one

            for ext in chunk:
                event = parsed.get(ext)
                if event is None:
                    continue
                stats["events_reached"] += 1
                if not sunk_event_is_open(event):
                    # #7930: hand it to the writer instead of binning it. The
                    # writer's own `_venue_open` branch stamps `status='resolved'`
                    # and `settled_at` in one statement, which is what stops the
                    # row being served as a live answer — and it is the SAME
                    # predicate, so there is no second rule to drift. No refusal
                    # is needed: the status write takes the row out of
                    # `_SUNK_POLY_WHERE`'s own `status = 'open'` test, durably and
                    # where SQL can see it, which a Redis refusal set cannot be.
                    stats["events_closed_at_venue"] += 1
                    to_write.append(event)
                    continue
                n_children, n_priced = sunk_event_child_census(event)
                stats["children_at_venue"] += n_children
                stats["children_priced_at_venue"] += n_priced
                if n_priced == 0:
                    stats["events_unpriced_at_venue"] += 1
                elif n_priced < n_children:
                    stats["events_partially_priced_at_venue"] += 1
                else:
                    stats["events_fully_priced_at_venue"] += 1
                # Unpriced events go to the writer too: its upsert is what stamps
                # `volume_updated_at`, which is what takes the row out of the
                # next six hours of passes. It writes no price for them.
                to_write.append(event)

            if to_write:
                await _process_event_batch(
                    to_write, stats["writer"], FuturesMarket, FuturesOutcome,
                    FuturesOddsSnapshot, pg_insert, probability_to_american,
                    compute_market_tier,
                )

            # Advance only over a batch that was READ. An unreadable batch
            # `continue`s above, so its rows are met again next lap at the
            # latest; a 429 or the deadline leaves the cursor before them.
            if stats["rate_limited"]:
                # A 429 on the direct arm ends the pass like a 429 on the batch
                # arm does, and on the same terms: "keep the cursor where it is,
                # retry next pass". The chunk's writes above still stand —
                # the batch payload behind them was a clean 200 and discarding
                # it would make backing off cost us data we already hold — but
                # the cursor must NOT advance, because the ids this chunk had
                # not yet asked about were abandoned, not answered. Advancing
                # would push them a full ~32-hour lap away for a reason that has
                # nothing to do with them.
                break

            # Advance only over a batch that was READ. An unreadable batch
            # `continue`s above, so its rows are met again next lap at the
            # latest; a 429 or the deadline leaves the cursor before them.
            done_rotate = [rotate_id_by_ext[e] for e in chunk if e in rotate_id_by_ext]
            if done_rotate:
                last_rotate_id_done = max(last_rotate_id_done, max(done_rotate))
    finally:
        await service.close()

    if rc is not None:
        try:
            rc.setex(_SUNK_POLY_CURSOR_KEY, 86400 * 7, str(last_rotate_id_done))
            if newly_refused:
                rc.sadd(_SUNK_POLY_REFUSED_KEY, *newly_refused)
                rc.expire(_SUNK_POLY_REFUSED_KEY, SUNK_POLY_STALE_HOURS * 3600)
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"redis write: {str(exc)[:80]}")

    # One sweep, after the writes, for the reason the poll gives.
    if stats["writer"]["events_processed"]:
        stats["sub_markets_linked"] = await link_polymarket_sub_markets()

    stats["cursor"] = last_rotate_id_done
    stats["elapsed_s"] = round(_time.monotonic() - started, 1)
    # Never "complete": one pass is one slice of a lap, and an event the venue
    # has not priced is not recovered however cleanly the pass ran.
    stats["terminal"] = (
        "rate_limited" if stats["rate_limited"]
        else "deadline" if stats["deadline_hit"]
        else "slice_done"
    )
    return stats


async def _backfill_polymarket_price_history(
    limit: int = 500,
    fidelity: int = 60,
    interval: str = "max",
    mode: str = "resolved_zero",
):
    """Backfill historical price data for Polymarket outcomes.

    Modes:
      resolved_zero — resolved markets with zero snapshots (calibration).
      open_sparse   — open/active feed-visible markets with no snapshots
                      in the last 7 days (chart quality for Discover).

    Uses the CLOB API /prices-history endpoint (works for both active
    and resolved markets, no API key required).
    """
    import asyncio
    import json as json_module
    from app.models.models import FuturesOddsSnapshot

    stats = {
        "mode": mode,
        "outcomes_processed": 0, "outcomes_skipped": 0,
        "snapshots_created": 0, "events_fetched": 0,
        "api_empty": 0, "errors": [],
    }

    try:
        from app.services.polymarket_api import PolymarketAPIService

        async with get_task_session() as session:
            if mode == "open_sparse":
                result = await session.execute(
                    text("""
                        SELECT fo.id, fo.external_id,
                               fm.external_id AS market_external_id
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.source = 'polymarket'
                          AND fm.status IN ('open', 'active')
                          AND (fm.image_url IS NOT NULL
                               OR fm.hook_description IS NOT NULL)
                          AND NOT EXISTS (
                              SELECT 1 FROM futures_odds_snapshots fos
                              WHERE fos.outcome_id = fo.id
                                AND fos.captured_at > NOW() - INTERVAL '7 days'
                          )
                        ORDER BY fm.updated_at DESC
                        LIMIT :limit
                    """),
                    {"limit": limit},
                )
            else:
                result = await session.execute(
                    text("""
                        SELECT fo.id, fo.external_id,
                               COALESCE(
                                   fm.market_metadata->>'polymarket_event_id',
                                   REPLACE(fm.group_id, 'polymarket:', ''),
                                   fm.external_id
                               ) AS market_external_id
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.source = 'polymarket'
                          AND fm.status = 'resolved'
                          AND NOT EXISTS (
                              SELECT 1 FROM futures_odds_snapshots fos
                              WHERE fos.outcome_id = fo.id
                          )
                        ORDER BY fm.updated_at DESC
                        LIMIT :limit
                    """),
                    {"limit": limit},
                )
            outcomes_to_backfill = result.fetchall()

            if not outcomes_to_backfill:
                return {**stats, "status": "nothing_to_backfill"}

            by_event: dict[str, list[dict]] = {}
            for row in outcomes_to_backfill:
                by_event.setdefault(row.market_external_id, []).append({
                    "outcome_id": row.id,
                    "condition_id": row.external_id,
                })

            logger.info(
                "PM price history backfill: %d outcomes across %d events",
                len(outcomes_to_backfill), len(by_event),
            )

            service = PolymarketAPIService()
            try:
                for event_id, outcomes in by_event.items():
                    event_data = await service.get_event_by_id(event_id)
                    if not event_data:
                        stats["errors"].append(f"event_{event_id}: not_found")
                        continue
                    stats["events_fetched"] += 1

                    token_map: dict[str, str] = {}
                    for market in event_data.get("markets", []):
                        cid = market.get("conditionId")
                        clob_ids_raw = market.get("clobTokenIds", "[]")
                        try:
                            clob_ids = json_module.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
                        except (json_module.JSONDecodeError, TypeError):
                            clob_ids = []
                        if cid and clob_ids:
                            token_map[cid] = clob_ids[0]

                    for outcome in outcomes:
                        cid = outcome["condition_id"]
                        token_id = (
                            token_map.get(cid)
                            or token_map.get(cid.rstrip("_yes").rstrip("_no"))
                        )
                        if not token_id:
                            stats["outcomes_skipped"] += 1
                            continue

                        try:
                            history = await service.get_prices_history(
                                token_id=token_id,
                                interval=interval, fidelity=fidelity,
                            )
                        except Exception as e:
                            stats["errors"].append(f"{outcome['outcome_id']}: {str(e)[:80]}")
                            continue

                        if not history:
                            stats["api_empty"] += 1
                            continue

                        from sqlalchemy.dialects.postgresql import insert as pg_insert
                        batch_values = [
                            {
                                "outcome_id": outcome["outcome_id"],
                                "bookmaker": "polymarket",
                                "probability": round(float(pt["p"]), 6),
                                "last_price": round(float(pt["p"]), 4),
                                "captured_at": datetime.fromtimestamp(pt["t"], tz=timezone.utc),
                            }
                            for pt in history
                            if pt.get("t") is not None and pt.get("p") is not None
                        ]

                        if batch_values:
                            for i in range(0, len(batch_values), 100):
                                stmt = pg_insert(FuturesOddsSnapshot).values(batch_values[i:i + 100])
                                await session.execute(stmt.on_conflict_do_nothing())
                            stats["snapshots_created"] += len(batch_values)

                            first_price = batch_values[0]["probability"]
                            if 0 < first_price < 1:
                                await session.execute(
                                    text("""
                                        UPDATE futures_outcomes
                                        SET opening_probability = :price,
                                            opening_source = 'clob_history'
                                        WHERE id = :oid
                                          AND opening_probability IS NULL
                                    """),
                                    {"price": first_price, "oid": outcome["outcome_id"]},
                                )

                        stats["outcomes_processed"] += 1
                        await asyncio.sleep(0.1)

                    await asyncio.sleep(0.1)

                await session.commit()
            finally:
                await service.close()

    except Exception as e:
        logger.error("PM price history backfill error: %s", e)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    return stats


def _is_placeholder_outcome(market) -> bool:
    """
    Detect Polymarket placeholder/reserved-slot markets.

    Polymarket pre-creates empty sub-markets for multi-outcome events before
    the real candidates are announced. These have names like "Player B",
    "Player S", "Player N" and typically:
      - outcomePrices = ["1", "0"] or [] (no real pricing)
      - bestBid = 0 or None (nobody is buying)
      - lastTradePrice = 0 or None (never traded)

    Without this filter, the "1.0" price makes them show up as 100% favorites.
    """
    import re

    # Check question or groupItemTitle for placeholder patterns
    name = market.group_item_title or market.question or ""

    # "Player XX" reserved-slot pattern — one OR MORE uppercase letters.
    # Polymarket switches to 2-letter suffixes ("Player AD", "Player AG") once a
    # field exceeds 26 slots; the original single-letter regex missed those, so
    # ~44 OPEN award/round-leader markets leaked anonymized "Player AD" @ ~0.5
    # across 7 sports (#953). The raw payload exposes no real name for these
    # (groupItemTitle="Player AD", prices=None, bid=0, lastTrade=0), so suppress.
    if re.match(r"^Player\s+[A-Z]+$", name.strip()):
        return True

    # "Will Player XX win/be/..." in the question
    if re.search(r"\bPlayer\s+[A-Z]+\b", market.question or ""):
        return True

    # Additional heuristic: no trading activity AND price is exactly 1.0
    # (real 100% favorites still have lastTradePrice > 0)
    #
    # ── #6110: ...AND THE VENUE HAS NOT SETTLED THE LEG ────────────────────
    #
    # "A real 100% favorite has traded" is a claim about a market that is still
    # BEING MADE. Once the venue closes a negRisk leg, ``outcomePrices[0]`` stops
    # being a quote and becomes the RESULT — and a winner nobody ever traded has
    # no last trade to show for itself. So a settled champion and a reserved slot
    # arrive here byte-identical, and this heuristic cannot tell them apart:
    #
    #     groupItemTitle "Other"   ("Will any other rider win the 2026 Vuelta?")
    #     closed=True  outcomePrices=["1","0"]  bestBid=0  lastTradePrice=0
    #
    # That leg is Enric Mas Nicolau winning the Vuelta a España 2026, confirmed
    # at BOTH venues (Kalshi settled ``KXCYCLING-26VLTA-EMAS`` ``result=yes``,
    # 1 of 184; Polymarket resolved this leg Yes, 1 of 71). We dropped it, so
    # market 58675941 stored 30 riders — every one of them correctly a loser —
    # and no champion at all. ``all_losers`` then said so in writing ("the
    # winning outcome isn't in our DB"), and a Grand Tour that finished showed
    # no winner.
    #
    # ``closed`` is the venue's own discriminator, already parsed onto the DTO:
    # a reserved slot is never closed while its event still trades. Read through
    # ``getattr`` so a duck-typed caller that carries no such field keeps exactly
    # the old behaviour rather than silently gaining the carve-out.
    #
    # The name patterns above are deliberately NOT relaxed. They run first and
    # unconditionally, so a settled ``Player AD`` is still suppressed; only a
    # NAMED leg the venue has settled at ~1.0 is admitted. A negRisk partition
    # settles exactly one such leg — measured on that event, 1 of 71 clears
    # 0.995 and it is the winner.
    #
    # 🔴 CORRECTION (lane1b, 2026-09-15, self-reported before CERT-2892 was
    # graded and merged over; int368's ledger row carries the desk's reasoning).
    # This comment used to end "…while all 40 unused ``Rider N`` slots settle at
    # 0 and are dropped by the caller's ``prob <= 0`` test." **That sentence was
    # false about this event and the population was carried across from #953
    # unread.** Re-read of Gamma ``/events?id=815313``: 71 legs, **zero** legs
    # matching an anonymous-slot pattern, and all 70 non-winning legs are NAMED
    # riders at ``outcomePrices[0] == 0``. ``_parent_outcome_data`` returns 31
    # rows rather than 1 because thirty of those legs price off a *last trade*
    # (0.005, 0.004, 0.002…), not off ``outcomePrices[0]`` — which is the
    # correct explanation of the row count and not the one that shipped here.
    # The load-bearing claim above is untouched and re-verified. One consequence
    # worth stating: because this event carries no anonymous slots at all, the
    # "a settled ``Player AD`` is still suppressed" paragraph has no specimen
    # here and its proof is synthetic: closed-and-settled ``Player B``/``AD``/
    # ``XX`` legs built by hand in
    # ``tests/test_polymarket_settled_champion_leg_6110.py``
    # (``test_a_settled_anonymised_slot_is_still_suppressed``).
    # Left as a correction rather than a silent deletion: the next reader
    # deserves to know the comment was wrong once, and about what.
    if (
        not getattr(market, "closed", False)
        and market.outcome_prices
        and market.outcome_prices[0] >= 0.995
    ):
        has_trading = (
            (market.best_bid is not None and market.best_bid > 0)
            or (market.last_trade_price is not None and market.last_trade_price > 0)
        )
        if not has_trading:
            return True

    return False


def complementary_book(
    yes_bid: float | None,
    yes_ask: float | None,
    yes_last_trade: float | None,
) -> tuple[float | None, float | None, float | None]:
    """The No token's book, read off the Yes token's book. An identity, not an estimate.

    In a binary CLOB the two tokens share one order book: a resting bid for No at
    ``q`` IS a resting ask for Yes at ``1 - q``. So the No side is not inferred
    here, it is the same orders addressed from the other token.

    CAL-P095 measured why this function has to exist. Population-wide, 0
    irreducible shards (``artifacts/cal-p095/leg_book_coverage.json``):

        over   248,702 legs — bid 76.98%, ask 99.14%
        under  248,702 legs — bid  0.00%, ask  0.00%
        yes    258,746 legs — bid 66.33%, ask 98.03%
        no     244,713 legs — bid  0.00%, ask  0.00%

    **493,415 Under/No legs and not one book**, because the decomposed-pair
    writer below passes ``market.best_bid`` / ``market.best_ask`` on the Over
    upsert and mentions neither column on the Under upsert. Every book-based
    predicate in the codebase — ``is_fabricated_midpoint`` (#1578),
    ``classify_fabricated_book`` (UX-P011 / #1574) — is therefore structurally
    blind on exactly half of every Polymarket pair, which is how a manufactured
    midpoint gets dropped on the Over leg while its Under partner survives to
    lead the card.

    It also cost the calibration program a wrong inference: CAL-P094 read the
    ``no_book`` verdict on ``baseball/quantity``'s 0.5000 spike as evidence that
    those legs never traded ("a leg that never had a book never had one"). They
    are NULL because nothing ever wrote them, at any price, for any market —
    gotcha #53, an absent column read as an absent book.

    NULL-preserving in both directions: a missing Yes-side counterpart yields
    ``None``, never a manufactured ``0``. That distinction is load-bearing
    downstream, where ``bid > 0`` and ``last_price > 0`` are liquidity tests and
    a fabricated zero would read as a real, empty book.

    The spread is invariant under the flip — ``(1-bid) - (1-ask) == ask - bid`` —
    so a book judged untradeable on one leg is judged untradeable on the other,
    and neither leg can launder the other past a spread test.

    This is a CAPTURE fix and stays clear of the fail-closed rule in
    :mod:`app.utils.pair_opening_coherence`. That rule governs **openings**,
    which become published forecasts through ``calibration_probability``'s
    fallback and must be refused rather than synthesised. These are evidence
    columns; recording the book that already exists is the opposite of inventing
    a price.

    Returns:
        ``(no_bid, no_ask, no_last_trade)``.
    """
    no_bid = None if yes_ask is None else 1 - float(yes_ask)
    no_ask = None if yes_bid is None else 1 - float(yes_bid)
    no_last = None if yes_last_trade is None else 1 - float(yes_last_trade)
    return no_bid, no_ask, no_last


def _unpriced_leg_external_ids(event) -> list[str]:
    """Condition ids the venue SERVED this pass but quotes no price for (#4000).

    The counterpart to :func:`_parent_outcome_data`, and it exists because
    ``continue`` throws away a fact we were told. When Gamma answers a negRisk leg
    with no price and a dead book, ``_parent_outcome_data`` drops the leg from the
    write set — correctly, there is no price to write — and the row we already
    hold keeps whatever number it was last given. **Declining to write is not the
    same as withdrawing what is written**, and for 2,545 rows across 105 open
    single-winner Polymarket fields the difference had been standing since
    2026-05-12: measured on production 2026-09-09, market 112897 (*Presidential
    Election Winner 2028*) carried 52 legs refreshed that day and 76 frozen at
    ``current_probability = 1.000000``, ``price_changed_at IS NULL``, untouched for
    120 days.

    Gamma is unambiguous about them and says so on every pass — for
    ``Will Person BG win the 2028 US Presidential Election?``::

        active=false  outcomePrices=None  bestBid=0  bestAsk=1
        lastTradePrice=0  volume=0

    So the leg is not delisted (it is still in ``GET /events/31552``'s 128 markets,
    beside the live ones) and it is not mispriced. It has no price, and our row
    claims certainty on its behalf.

    Two safeties are structural rather than heuristic, which is why the retirement
    is keyed on the payload instead of on a database sweep:

    * **A leg the pass did not cover can never be retired.** Only ids present in
      ``event.markets`` are returned, so a truncated or partial payload withdraws
      nothing — it simply names fewer legs.
    * **A refused price is not an absent price.** ``_resolve_market_probability``
      also returns ``None`` when it *distrusts* a quote the venue really is making
      (the #151 evidence gate, the fabricated-midpoint test). Retiring those would
      un-price live markets, so a leg with any bid or any trade behind it is
      excluded here even though it is unpriced by us.

    Scoped to negRisk multi-market events: that is the whole measured population
    (every one of the 84 tier-1/2 markets is ``mutually_exclusive`` + ``field`` +
    polymarket), and the other two shapes in ``_parent_outcome_data`` price through
    different gates whose refusals mean different things.
    """
    if not (event.neg_risk and len(event.markets) > 1):
        return []

    unpriced: list[str] = []
    for market in event.markets:
        if not market.condition_id:
            continue
        if _resolve_market_probability(market) is not None:
            continue  # the venue is quoting; nothing to withdraw
        bid = market.best_bid
        if bid is not None and float(bid) > 0:
            continue  # a real bid — we refused it, the venue did not
        last = market.last_trade_price
        if last is not None and float(last) > 0:
            continue  # it has traded — that is evidence, not an absence
        unpriced.append(market.condition_id)
    return unpriced


async def _retire_unpriced_legs(session, futures_market_id: int, external_ids) -> int:
    """Withdraw our number on legs the venue quotes no price for. Returns the count.

    ``current_probability``/``current_american_odds`` only — the two fields that
    render. Deliberately NOT touched:

    * ``opening_probability``. These rows carry a frozen ``1.000000`` opening too,
      which is the permanent half of the damage ``winner_field_coherence`` warns
      about, but opening is calibration-truth and is graded by a different owner;
      withdrawing it here would be a curve change wearing an ingest fix's clothes.
      Filed separately with the numbers.
    * ``is_winner IS TRUE`` rows. A crowned leg's price is its settlement, not a
      quote, and nothing about an empty book afterwards makes the grade untrue.
    * ``last_updated``. Tempting, and wrong: the touch-columns are what freshness
      consumers read, and ``routes/playoffs.py`` drops an outcome from the grid on
      a stale stamp. Stamping a retirement fresh would advertise "we have a current
      price for this leg" at the exact moment we stopped having one, and could
      promote a blank cell into a grid that was correctly dropping it. The row's
      old stamp is the honest one — we have nothing newer. The retirement is made
      observable through the ``legs_retired`` task stat and the log line instead,
      which is where an ingest event belongs.
    """
    ids = list(external_ids)
    if not ids:
        return 0
    from sqlalchemy import update
    from app.models import FuturesOutcome

    result = await session.execute(
        update(FuturesOutcome)
        .where(
            FuturesOutcome.market_id == futures_market_id,
            FuturesOutcome.external_id.in_(ids),
            FuturesOutcome.current_probability.isnot(None),
            FuturesOutcome.is_winner.isnot(True),
        )
        .values(
            current_probability=None,
            current_american_odds=None,
        )
    )
    return int(result.rowcount or 0)


def _last_trade_survives_own_book(market) -> float | None:
    """The leg's last trade, or ``None`` when its OWN live book prices it out (#7548).

    Every place this file substitutes ``lastTradePrice`` for a quote rests on one
    sentence — "somebody actually transacted there, so it is a belief". Q428
    already bounded that sentence in TIME (the 24-hour volume test). This bounds it
    against the other thing Gamma sends in the same payload: the book.

    WHAT A READER SAW. ``/futures/56947465`` (*NASCAR Cup Series: 2026 Champion*)
    drew Kyle Larson spiking to **98.9%** for one stamp (2026-09-19T20:31:08Z) in a
    week otherwise near 19-25%, on the Probability Trend AND the hero sparkline.
    The venue's own tape for that condition (data-api ``/trades``, saved) shows a
    ladder of 46-share market buys walking an empty ask side at 20:00:48-20:01:27Z
    and ONE 46-share print at **0.989** at 20:10:35Z — about $45. The venue's own
    minute series (CLOB ``/prices-history``, saved) never exceeds 0.586 that day
    and reads 0.3815-0.3935 across 20:30-20:32Z; a midpoint of 0.39 is
    arithmetically impossible with an ask at or above 0.989 (it would need a
    negative bid), so at our capture instant the ask sat far BELOW the print. We
    chose the venue's stalest number over its freshest one. Identity was never in
    question: right event, right condition, right YES token.

    THE RULE IS NOT NEW AND IS NOT RE-DERIVED. ``book_refutes_price`` is #5121's
    shipped predicate — "the trade is a memory; the quote is an offer" — written
    for ``_kalshi_yes_probability`` rule 2 on exactly this shape (12 of 12 rungs
    storing the venue's ``last_price`` above the venue's own ask). It is imported,
    with its own half-cent tolerance and its own empty-book carve-out. Polymarket
    ticks are 0.001-0.01, so half a cent is at least as conservative here as on
    Kalshi's cent grid: it can only refute LESS.

    WHAT SURVIVES, BY CONSTRUCTION AND NOT BY EXEMPTION:

    * **A genuine near-100% move.** A leg that really ran to 0.99 has a book up
      there (or a cleared one). ``bid 0.985 / ask 0.992 / last 0.989`` is inside
      its book; ``ask None`` or ``ask 1.0`` cannot be exceeded. Gotcha #19's
      blowout is the second shape and is untouched.
    * **A price that is not a substituted trade.** This is asked only where a
      last trade is about to stand in for a quote. ``outcome_prices`` that pass
      the existing gates are returned before any of these sites is reached —
      Larson today reads 0.2505 off ``outcome_prices`` beside ``last 0.175`` and
      ``bid 0.223``, a trade BELOW the bid, and nothing here looks at it.

    A REFUSAL IS A SKIP, the same as every other refusal in this resolver: the
    caller writes nothing for the leg on this pass, the row keeps its last
    supported number, and the chart shows an honest gap at that stamp. It does NOT
    fall through to the ask-only fallback — that would print one side of the same
    wide book this file already refuses to average.
    """
    last = market.last_trade_price
    if last is None or not (0 < float(last) < 1):
        return None
    if book_refutes_price(market.best_bid, market.best_ask, float(last)):
        return None
    return float(last)


def _parent_outcome_data(event) -> list[dict]:
    """The PARENT market's outcome rows for one Gamma event. Pure, no DB, no network.

    Extracted from ``_process_event_batch`` (#3613) so the hourly poll and the
    dark-market refresh below cannot drift into two different ideas of what a
    Polymarket event's parent price is. Both call this and nothing else.

    The three shapes are the poll's own, unchanged, and the difference between
    them is deliberate — folding them together would be a pricing change wearing
    a refactor's clothes:

    * **negRisk multi-market** — a single-winner partition, so each sub-market IS
      one leg. Priced through :func:`_resolve_market_probability`, which applies
      the placeholder filter and the #151 evidence gate.
    * **non-negRisk multi-market** (a game: moneyline + spread + O/U + props) —
      the parent keeps a leg per sub-market for the moneyline matching task, and
      it takes Gamma's precomputed ``outcome_prices[0]`` RAW, bypassing those two
      gates. #1578 recorded that as the least-guarded of the five write paths and
      deliberately added only the phantom-midpoint test to it; that judgement is
      preserved here rather than quietly tightened.
    * **single-market** — priced through the gated resolver and named "Yes"
      unless the venue named a side (#6739). TWO legs when the venue named
      BOTH sides — a sole-moneyline game, which never reaches the
      decomposition branch — and one otherwise, which keeps every genuine
      Yes/No question byte-identical (#7505; see the branch's own note).

    Returns the rows unsorted and unranked; the caller sorts, ranks and writes.
    """
    outcome_data: list[dict] = []

    if event.neg_risk and len(event.markets) > 1:
        for market in event.markets:
            prob = _resolve_market_probability(market)
            if prob is None or prob <= 0:
                continue
            # Prefer groupItemTitle (e.g., "33°F or below") over question
            # parsing; Q492 rescues the case where both collapse onto the
            # event's own title and so name no side.
            outcome_data.append({
                "external_id": market.condition_id,
                "name": _leg_label(market, event.title),
                "prob": prob,
                "yes_bid": market.best_bid,
                "yes_ask": market.best_ask,
                "last_price": market.last_trade_price,
                # #2027 / CERT-3202: the sub-market this leg was priced FROM.
                # Carried so the parent-field writers can ask the same question
                # the decomposed path already asks — is THIS child settled —
                # instead of passing `market=None` and seeing only the parent's
                # flags. A closed sole child under an open parent was banking
                # its settled book as the opening line.
                "market": market,
            })
        return outcome_data

    if len(event.markets) > 1:
        for market in event.markets:
            prob = market.outcome_prices[0] if market.outcome_prices else None
            # #6676: the same pair, for the same reason, as in
            # `_resolve_market_probability_with_source` — read the long comment
            # there. This is the least-guarded of the five write paths (#1578), and
            # outcome 61246705 reached a /sports card through THIS branch, not the
            # resolver, so guarding only the resolver would have fixed two of the
            # three named rows and left the parent anchor printing 50%.
            if is_fabricated_midpoint(
                prob, market.best_bid, market.best_ask
            ) or is_empty_book_midpoint(prob, market.best_bid, market.best_ask):
                # #7548: ...and only a trade the leg's own book has not priced out.
                prob = _last_trade_survives_own_book(market)
            if prob is None or prob <= 0:
                continue
            # Q492: this is the parent anchor of a game-level event, and its
            # moneyline leg is exactly the one Polymarket sends with no
            # groupItemTitle — the case that produced a price labelled with
            # the whole matchup.
            outcome_data.append({
                "external_id": market.condition_id,
                "name": _leg_label(market, event.title),
                "prob": prob,
                "yes_bid": market.best_bid,
                "yes_ask": market.best_ask,
                "last_price": market.last_trade_price,
                # #2027 / CERT-3202: the sub-market this leg was priced FROM.
                # Carried so the parent-field writers can ask the same question
                # the decomposed path already asks — is THIS child settled —
                # instead of passing `market=None` and seeing only the parent's
                # flags. A closed sole child under an open parent was banking
                # its settled book as the opening line.
                "market": market,
            })
        return outcome_data

    for market in event.markets:
        prob = _resolve_market_probability(market)
        if prob is None or prob <= 0:
            continue
        # #6739: the THIRD writer of the pair #6050 fixed on the other two, and
        # the only one that never asked. A Polymarket event carrying ONE market
        # is not always a Yes/No question — a game whose venue listing holds just
        # the moneyline arrives here too, with `question` set to the matchup and
        # the two sides in `outcomes`. Hardcoding "Yes" threw that away: measured
        # 2026-09-19 over 240 stored single-leg rows, 223 of them sit under a
        # matchup whose venue payload reads `outcomes: ["Jukurit Mikkeli",
        # "Vaasan Sport"]`, so the page printed "Yes 62%" and, once the match
        # settled, a bare "Settled" chip with no winner (32 such events).
        #
        # `outcomes[0]` is the array parallel to `outcome_prices`, which is the
        # field `_resolve_market_probability` prices this leg from — so the label
        # is definitionally the side this number belongs to and there is no
        # orientation guess here. The remaining 17 are genuine Yes/No questions:
        # the helper returns the fallback for them and they stay byte-identical.
        sub_name = market.question or event.title
        side_name = _sub_market_side_label(market, 0, sub_name, "Yes")
        outcome_data.append({
            "external_id": market.condition_id,
            # Called inline, not passed as `side_name`: Q492's wiring guard
            # reads this expression out of the AST and requires it to BE a
            # shared-labeller call, so binding it to a local would read as a
            # writer that names its leg some other way. The local above is the
            # same pure call, kept for the partner condition below.
            "name": _sub_market_side_label(market, 0, sub_name, "Yes"),
            "prob": prob,
            "yes_bid": market.best_bid,
            "yes_ask": market.best_ask,
            "last_price": market.last_trade_price,
            # #2027 / CERT-3202: see the note on the branches above.
            "market": market,
        })

        # #7505: and the OTHER side, which #6739 named and never wrote.
        #
        # #6739 established that a single-market event is often a game whose
        # venue listing holds just the moneyline, and taught leg 0 to wear the
        # side's name instead of "Yes". It stopped there, so the row kept ONE
        # leg: production served "Davis Cup: Liam Draxl vs. Quentin Halys —
        # Liam Draxl 50%", a half-filled comparative bar with one name on it,
        # and a reader cannot tell whether Halys is the other half or simply
        # unpriced. Measured at the venue 2026-09-21 (notice 26/27, Gamma
        # `/events/1045485`, slug `daviscup-draxl-halys-2026-09-19`): ONE
        # market, `outcomes: ["Liam Draxl", "Quentin Halys"]`, `outcomePrices:
        # ["0.5", "0.5"]`. Both sides are published. The second leg was one
        # index away, exactly as leg 0's label was before #6739.
        #
        # The two-sided shape is not new: an event with >1 market gets a
        # decomposed `{condition}_yes`/`_no` row carrying both sides, which is
        # why an NHL game reads correctly and a Davis Cup rubber does not —
        # the decomposition branch is gated on `len(event.markets) > 1` and a
        # sole-moneyline event never reaches it. This writes the same pair the
        # decomposed row would have, onto the only row these events have.
        #
        # 🔴 THE KEY IS DELIBERATELY NOT `{condition}_no`, AND THAT IS THE
        # WHOLE TRAP. `duplicate_condition_outcomes.drop_duplicate_legs` drops
        # a leg whose id ends `_yes`/`_no` when the BARE condition id is also
        # on the same market — which is precisely this pair — and it runs at
        # SERVE time in `routes/feed.py`, `routes/events.py` and six places in
        # `routes/futures.py`. Keyed `_no`, this leg would be written on every
        # poll and filtered out of every reader surface: inert on exactly its
        # own population, the failure #6739's own sibling rail was written to
        # avoid. `_side1` is outside `BINARY_LEG_SUFFIXES`, so the dedup rule
        # correctly reads it as a rung rather than a duplicate of one.
        #
        # It also lands the leg on the RIGHT history series rather than merely
        # dodging the filter: `generic_market_history.wanted_gamma_outcome_name`
        # resolves a non-suffixed id BY NAME ("BY NAME, NEVER BY POSITION",
        # Q489), and the name here is the venue's own `outcomes[1]` token, so
        # the complement's chart asks Gamma for the Halys token by the label
        # Gamma itself published.
        #
        # The price is `1 - prob`, NOT the raw `outcome_prices[1]`. Leg 0 is
        # priced through the gated resolver (0.495 where the venue posts 0.49),
        # so taking the raw complement would serve a pair summing to 1.005 —
        # a visibly incoherent two-way card. The complement of the number we
        # actually store is what the decomposed sibling holds for the same
        # game (Hurricanes 0.495 / Flames 0.505, market 61814743), so the two
        # rows agree instead of disagreeing by half a point.
        #
        # A genuine Yes/No question stays BYTE-IDENTICAL: `_sub_market_side_label`
        # returns the caller's fallback for every degenerate shape (outcomes
        # absent, token blank, token a bare Yes/No, token echoing the question),
        # so requiring BOTH sides to be named is what keeps the 17 measured
        # real binaries — and every o/u single-market, whose fallback short-
        # circuits the helper — writing exactly one leg as before.
        if side_name != "Yes" and len(getattr(market, "outcomes", None) or []) > 1:
            comp_fallback = "Under" if "o/u" in sub_name.lower() else "No"
            comp_name = _sub_market_side_label(market, 1, sub_name, comp_fallback)
            if comp_name != comp_fallback:
                comp_bid, comp_ask, comp_last = complementary_book(
                    market.best_bid,
                    market.best_ask,
                    market.last_trade_price,
                )
                outcome_data.append({
                    "external_id": f"{market.condition_id}_side1",
                    # Inline for the same reason as leg 0 above.
                    "name": _sub_market_side_label(market, 1, sub_name, comp_fallback),
                    "prob": 1 - prob,
                    "yes_bid": comp_bid,
                    "yes_ask": comp_ask,
                    "last_price": comp_last,
                    "market": market,
                })
    return outcome_data


def _resolve_market_probability(market) -> float | None:
    """Resolve the Yes-side probability, discarding which source produced it.

    Thin wrapper over :func:`_resolve_market_probability_with_source` for the call
    sites that only want the number. Kept as the primary name because most of them
    do, and because changing every caller to unpack a tuple would put churn in
    files this fix has no business touching.
    """
    prob, _source = _resolve_market_probability_with_source(market)
    return prob


def _resolve_market_probability_with_source(market) -> tuple[float | None, str | None]:
    """
    Resolve the Yes-side probability for a Polymarket market, and name its source.

    Priority: outcomePrices[0] → bid/ask midpoint → lastTradePrice.

    THE SOURCE IS RETURNED BECAUSE THE PAIR WRITER NEEDS IT. Only
    ``outcome_prices`` is a leg of the same upstream-normalised pair as
    ``outcome_prices[1]``; a midpoint we computed, a trade from an earlier moment,
    and a one-sided ask are all different instruments. Writing the Under leg from
    the raw complement while the Over leg came from one of those built pairs that
    sum to 1 only by luck — measured at 5,566 markets, 631 of them still arriving
    after the 2026-07-08 Under-side fix. See
    :mod:`app.utils.pair_opening_coherence`, which is the gate that consumes this.

    A source label is only meaningful alongside a non-None probability; every
    ``return None`` path below returns ``(None, None)``.

    Skips placeholder markets that Polymarket creates as reserved slots
    (e.g., "Player B", "Player S"). These have:
      - empty outcomePrices ([]) or ["1", "0"]
      - bestBid = 0 or None
      - bestAsk = 1 (max spread, no real market-making)
      - lastTradePrice = 0 or None
    Without this filter, the ask-only fallback or the raw 1.0 price would
    set prob = 1.0 (100%), making placeholders look like favorites.
    """
    # Reject known placeholder markets before examining prices
    if _is_placeholder_outcome(market):
        return None, None

    # #151 cp-capture guard: real price discovery leaves orderbook/trade evidence.
    # A live bid, a real (sub-max) ask, or a last trade all count. Gamma's
    # precomputed ``outcomePrices`` is populated for reserved/untraded slots too,
    # so trusting it blind seeded ~150K resolved poly outcomes near ~0.50 that
    # actually resolve ~0.19 (win-rate census, Queue #151) — dragging poly
    # calibration MCE to 4.01. Require this evidence for MID-RANGE prices only;
    # extreme prices (<=0.05 / >=0.95) can legitimately have a cleared book
    # (near-certain outcomes) and are left permissive.
    has_market = (
        (market.best_bid is not None and market.best_bid > 0)
        or (market.last_trade_price is not None and market.last_trade_price > 0)
        or (market.best_ask is not None and 0 < market.best_ask < 0.99)
    )

    prob = market.outcome_prices[0] if market.outcome_prices else None

    # #1578: Gamma's precomputed price, when it IS the midpoint of an untradeable
    # book, is a number nobody will trade at. Decline it here — ahead of the
    # `return prob` below, which is where the phantom actually enters (NOT the
    # midpoint fallback further down; a guard placed there would change nothing).
    #
    # Both conditions are required, and the second is not pedantry. `outcome_prices`
    # is opaque: usually the midpoint, but not always. When Gamma's number is
    # something OTHER than the midpoint of a wide book it came from elsewhere, and
    # the #151 evidence gate below is the right judge of it — that is what keeps a
    # real sub-max ask with no bid working. Sharing the read side's function rather
    # than restating the test is what makes "untradeable" mean one thing in this
    # codebase, and it is the exact predicate the production census measured:
    # 179,888 outcomes, and the 1,580 graded ones win 0.13% while asserting 50%.
    #
    # Trade evidence beats a wide book, the same priority _kalshi_yes_probability
    # uses: somebody actually transacted there, so it is a belief even when the
    # current quotes are garbage.
    #
    # Q428: "somebody actually transacted there" is a claim about the PRESENT,
    # and `lastTradePrice` carries no time. Measured on the 2026-08-28 US Open
    # bracket grid, that unbounded exception is what put Novak Djokovic at 71%
    # to reach the round of 16 and 79% to reach the quarter-final behind it —
    # a monotonicity violation on the page, sourced from ONE $5 trade against a
    # book quoted 7c bid / 98c ask. So the exception now checks the claim it
    # already rests on, using Gamma's own 24-hour window rather than a number
    # this file chose: a trade beats a wide book while the market is still being
    # traded, and stops beating it once nobody is.
    #
    # This is not a liquidity floor and there is no dollar threshold to tune —
    # the measured 24-hour-volume distribution on that population runs
    # continuously from $0 to $1,900 with no empty band to put one in, so any
    # floor would be a knob. The test is presence.
    #
    # Gotcha #19's case survives BY CONSTRUCTION, not by exemption. A blowout is
    # a market that ran away DURING active trading — the book clears because
    # everyone is on one side, not because nobody is there — so it carries
    # 24-hour volume and this branch cannot reach it.
    # #6676: the 0.0005 equality above is an EXACT-midpoint test, and it assumes
    # Gamma's payload describes one instant. It does not. `outcomePrices` and
    # `bestBid`/`bestAsk` can be a tick apart in the same response — caught live on
    # market 4630453 at 2026-09-17T03:43Z, price 0.5 beside quotes 0.03 / 0.98 while
    # Gamma's own `spread` field still read 0.94. Half a cent off the arithmetic mean
    # is past a 0.0005 tolerance, and the 2c/3c bid then satisfies the #151 evidence
    # gate below, so an empty never-traded book was stored as a 50% forecast. Three
    # such rows reached /sports as "Over 50% / Under 50%" cards on 2026-09-16.
    #
    # The remedy is the sibling predicate rather than a looser tolerance here,
    # because the two have complementary blind spots and widening either one alone
    # spends a population neither measured:
    #
    #   is_fabricated_midpoint  wide book coverage (spread >= 0.20), razor tolerance
    #                           (0.0005) — catches the 206 of 209 wide-book markets
    #                           that sat EXACTLY on their midpoint in the 03:41Z scan.
    #   is_empty_book_midpoint  a quote that bounds nothing (spread >= 0.90 since
    #                           #6727; two bounds, bid <= 0.05 AND ask >= 0.95,
    #                           before it), generous tolerance (0.01) — for #5247's
    #                           "a venue's own mid is not obliged to be the exact
    #                           arithmetic mean of the two sides it reports".
    #
    # #5247 documented that on the SERVE side and never applied it to the writer;
    # this is the line that makes ingest and serve read the same rows the same way.
    # Nothing here is a new threshold: both predicates are imported, not restated.
    #
    # #5333 CLOSED THE 3c ESCAPE (2026-09-17): `EMPTY_BOOK_MAX_BID` moved 0.02 -> 0.05
    # on its own measurement, so the live specimen above — 0.5 on 0.03 / 0.98 — is now
    # refused here rather than written. Nothing in THIS block changed; the constant is
    # imported, and `feed_market_quality` carries the measurement, the derived band
    # and the cost. The tests that pinned the escape open have flipped, which is how
    # #5333 was required to announce itself.
    #
    # #6727 THEN CLOSED THE ASK SIDE BY CHANGING SHAPE (same day): the two bounds are
    # one statement about the spread, so the pair became `ask - bid >= 0.90` — a
    # strict superset (0 of 132,550 production rows lost) that also catches the
    # compensated book the pair could not see, e.g. 0.01 / 0.94. Again nothing in
    # THIS block changed. The band it can reach is [0.44, 0.56] and, because the
    # spread ties the two sides together, it cannot widen further at any ask.
    #
    # A traded 50% still survives HERE, and the mechanism is a substitution, not a
    # keep: the volume-gated exception below runs after this test and returns
    # `last_trade_price` rather than the midpoint. 🪤 That protection does NOT reach
    # the serve path, because the label it produces is consumed by
    # `classify_pair_opening` and never persisted — so a genuine traded 0.50 stored
    # here on a 3c/97c book is still withdrawn by the reader's copy of the predicate.
    # Measured at 2 rows of 1,119; see `feed_market_quality`. Do not describe the
    # serve side as preserving traded 50%.
    if is_fabricated_midpoint(
        prob, market.best_bid, market.best_ask
    ) or is_empty_book_midpoint(prob, market.best_bid, market.best_ask):
        recently_traded = bool(market.volume_24h and float(market.volume_24h) > 0)
        # #7548: Q428 bounded "somebody transacted there" in TIME. The same payload
        # also carries the book, and a print the live ask (or bid) has moved past
        # is a memory, not a belief — see `_last_trade_survives_own_book`.
        surviving_trade = _last_trade_survives_own_book(market)
        if recently_traded and surviving_trade is not None:
            return surviving_trade, "last_trade_price"
        return None, None

    if prob is not None and prob > 0:
        # A mid-range outcomePrice with no orderbook and no trade is a
        # placeholder/synthetic quote, not price discovery — skip the snapshot
        # (it is re-captured next cycle once a real bid/trade appears).
        if 0.05 < prob < 0.95 and not has_market:
            return None, None
        return prob, "outcome_prices"

    # Midpoint fallback: both bid and ask must be present and positive, and the
    # book must be tradeable. #1578: a midpoint WE compute from a wide book is
    # fabricated by construction — there is no opacity here to give it the benefit
    # of the doubt, unlike Gamma's price above. Skipping it falls through to the
    # last-trade fallback directly below, which is precisely the priority
    # _kalshi_yes_probability uses (tight book -> midpoint; wide -> real trade).
    if (market.best_bid is not None and market.best_bid > 0
            and market.best_ask is not None and market.best_ask > 0
            and not _poly_book_is_untradeable(market.best_bid, market.best_ask)):
        return (market.best_bid + market.best_ask) / 2, "bid_ask_midpoint"

    # Last trade fallback
    if market.last_trade_price is not None and market.last_trade_price > 0:
        # #7548: a print the leg's own live book prices out is declined, and the
        # decline is a SKIP — it must not fall through to the ask-only fallback
        # below, which would publish one side of the book this path just refused.
        if book_refutes_price(
            market.best_bid, market.best_ask, float(market.last_trade_price)
        ):
            return None, None
        return market.last_trade_price, "last_trade_price"

    # Ask-only fallback: reject if ask >= 0.99 (placeholder/no real market)
    if (market.best_ask is not None
            and market.best_ask > 0
            and market.best_ask < 0.99):
        return market.best_ask, "best_ask"

    # No reliable price — skip this market
    return None, None


def _label_key(value: str | None) -> str:
    """Whitespace- and case-insensitive comparison key for an outcome label."""
    return " ".join((value or "").split()).casefold()


def _leg_label(market, event_title: str) -> str:
    """The display label for this market's index-0 (Yes-side) price.

    Q492. Both writers below resolve ``outcome_prices[0]`` and then named it from
    ``groupItemTitle``, falling back to question parsing. Neither names a *side*.
    For a game-level matchup Polymarket sends the moneyline with
    ``groupItemTitle: null`` and the question set to the event's own title, so
    ``_extract_outcome_name``'s "short enough, use it directly" fallback labelled
    the price with the whole matchup — a card reading
    "US Open WTA: Iga Swiatek vs Nadia Podoroska 89.5%". 89.5% of *what*? The
    number names no side, and the reader cannot recover one.

    ``outcomes`` is the parallel array to ``outcome_prices``, so ``outcomes[0]``
    is the only label that is definitionally the leg this price belongs to — the
    same rule as Q489, where a CLOB tick had to land on the leg whose book it
    was. It is used only to rescue a label that has collapsed onto the market's
    own name; an informative ``groupItemTitle`` ("Set 1 Winner", "33°F or below")
    is left exactly as it was.

    A bare Yes/No token is not a rescue — it names no side either — so a leg that
    can only be described by its parent's title keeps that title rather than
    being relabelled "Yes".
    """
    derived = (market.group_item_title or "").strip() or _extract_outcome_name(
        market.question, event_title
    )
    if _label_key(derived) != _label_key(event_title):
        return derived

    tokens = list(getattr(market, "outcomes", None) or [])
    token = (tokens[0] or "").strip() if tokens else ""
    if not token or _label_key(token) in _YES_NO_LABELS:
        return derived
    if _label_key(token) == _label_key(event_title):
        return derived
    return token


# A leg labelled only "Yes"/"No" names no side, so it is never a rescue for a
# label that has collapsed onto the market's own name (see :func:`_leg_label`).
_YES_NO_LABELS = frozenset({"yes", "no"})


def _sub_market_side_label(market, index: int, sub_name: str, fallback: str) -> str:
    """The label for a decomposed sub-market's ``outcome_prices[index]`` side.

    #6050. :func:`_leg_label` already settled this question for the PARENT
    writer (Q492) and the decomposed sub-market writer never inherited it, so
    the two paths disagreed about the same venue field. The sub-market writer
    named both sides positionally — ``"Yes"``/``"No"`` unless the name said
    "o/u" — which is right for a sub-market whose own name asks the question
    ("Both Teams to Score", "D/ST Touchdown") and wrong for a game moneyline,
    where Polymarket sends ``question`` set to the matchup itself and puts the
    two sides in ``outcomes``. Production served
    "Broncos vs. Chiefs — Yes 43.5% / No 56.5%" while the venue's own payload
    for that condition read ``outcomes: ["Broncos", "Chiefs"]``: the reader
    cannot recover which team "Yes" is, and the answer was one field away.

    ``outcomes`` is the parallel array to ``outcome_prices`` (the same rule
    :func:`_leg_label` rests on), so ``outcomes[index]`` is definitionally the
    side this price belongs to — there is no orientation guess here.

    Deliberately a RESCUE and not a rename: the venue's token is taken only
    when it actually names a side. A bare ``Yes``/``No`` token names no side
    either, and a token equal to the sub-market's own name reproduces the
    collapse we are trying to undo, so both keep ``fallback``. That is what
    keeps every genuine Yes/No sub-market — the large majority — byte-identical.
    """
    if _label_key(fallback) not in _YES_NO_LABELS:
        # "Over"/"Under" already names its side; never second-guess it.
        return fallback

    tokens = list(getattr(market, "outcomes", None) or [])
    if index >= len(tokens):
        return fallback

    token = (tokens[index] or "").strip()
    if not token or _label_key(token) in _YES_NO_LABELS:
        return fallback
    if _label_key(token) == _label_key(sub_name):
        return fallback
    return token


def _carry_venue_side_name(update: dict, label: str, fallback: str) -> dict:
    """Add ``name`` to an ON CONFLICT DO UPDATE set — but only when it is news.

    CERT-2820's required repair, ``6050-RENAME-EXISTING-OUTCOMES-ON-CONFLICT``.
    #6050 named the two sides correctly at INSERT, and every row the defect is
    ABOUT already exists: the 20 measured bare-matchup markets are reached only
    by the conflict arm, whose set dicts omitted ``name``. So each one would have
    gone on reading "Yes" forever while the fix reported success — inert on
    exactly its own population, which is the one place a rename cannot afford to
    be.

    🔴 **ONLY WHEN THE VENUE NAMED THE SIDE, AND THAT IS WHAT ``!= fallback``
    MEANS.** :func:`_sub_market_side_label` returns the caller's fallback for
    every degenerate shape — outcomes absent, token blank, token itself a bare
    Yes/No, token echoing the sub-market's own name. An unconditional write would
    therefore let ONE malformed payload rename a correctly stored "Broncos" back
    to "Yes", turning a poll hiccup into a visible regression on the very card
    this repairs. The comparison keeps the helper's fallbacks doing their job
    instead of overwriting the row with them.

    A genuine Yes/No sub-market — the large majority — takes the same branch and
    needs no write at all: its stored name is already the fallback, so skipping
    is not a compromise there, it is a no-op. That is also what keeps this
    statement byte-identical for every market that was never wrong.

    Returns the same dict, mutated, so a call site reads as one line.
    """
    if label != fallback:
        update["name"] = label
    return update


def _extract_outcome_name(question: str, event_title: str) -> str:
    """
    Extract a clean outcome name from a Polymarket market question.

    For negRisk markets, the question is often like:
    "Will the Los Angeles Lakers win the 2025-26 NBA Championship?"
    We want to extract "Los Angeles Lakers".

    Falls back to the full question if extraction fails.
    """
    if not question:
        return "Unknown"

    # Common patterns: "Will X win...", "Will X be...", "X to win..."
    import re

    # "Will the X win/be/become..."
    match = re.match(
        r"^Will\s+(?:the\s+)?(.+?)\s+(?:win|be|become|make|reach|qualify|finish)\b",
        question,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # "X to win..."
    match = re.match(
        r"^(.+?)\s+to\s+(?:win|be|become|make|reach)\b",
        question,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # If question is short enough, use it directly (minus trailing ?)
    cleaned = question.rstrip("?").strip()
    if len(cleaned) <= 60:
        return cleaned

    # Last resort: use first 60 chars
    return cleaned[:60]


def settle_outcomes_stmt(price: str, is_winner: str):
    """`_sync_polymarket_resolved_status`'s settling UPDATE, for one side.

    #7767. A module-level builder rather than two `text()` blocks inline in the
    sweep, for one reason: the real-Postgres gate
    (`tests/integration/test_polymarket_resolved_candidate_sql_pg.py`) can then
    EXECUTE the shipped statement instead of a retyped copy of it, which is that
    file's own standing rule — "a copy would pass while the shipped query was
    broken, which is the whole failure mode". There is no second spelling of
    this SQL anywhere.

    Three clauses, each carrying its own rule:

    * :func:`settled_price_set_sql` (#5246) writes the terminal price, nulls the
      american odds, and stamps `price_changed_at` only on a real move (#2024).
    * :func:`settlement_pending_sql` (#7767) decides whether the row still needs
      the write. It replaced `resolution_source <> 'api_settlement'`, which
      keyed the skip on the one column a half-finished settlement already had
      right and so sealed 217 legs out of their own repair.
    * ``DUPLICATE_CONDITION_LEG_SQL`` (Q487) keeps a suffixed duplicate of an
      id-anchored leg from being settled beside the row it duplicates.

    :param price: :data:`SETTLED_YES_PRICE` or :data:`SETTLED_NO_PRICE`; both
        fragments are driven off this one literal, so the side the WHERE tests
        for is by construction the side the SET writes.
    :param is_winner: the matching SQL boolean literal.
    """
    return text(
        "UPDATE futures_outcomes fo\n"
        "   SET is_winner = " + is_winner + ",\n"
        "       resolution_source = 'api_settlement',\n"
        "       " + settled_price_set_sql(price) + "\n"
        " WHERE fo.external_id = ANY(:cids)\n"
        "   AND " + settlement_pending_sql(price) + "\n"
        "   AND " + DUPLICATE_CONDITION_LEG_SQL
    )


async def _sync_polymarket_resolved_status():
    """Mark finished Polymarket markets resolved, addressing Gamma by event id.

    The regular polling task only fetches active events, so once a Polymarket
    event closes we never see it again and the market status stays ``open`` in
    our DB. This blocks all downstream pipelines (calibration, winner backfill,
    snapshot backfill). This task is the Polymarket equivalent of Kalshi's
    settled events backfill Phase 1 (gotcha #97).

    **#2637 — it could only ever see 2021, and this is the rewrite.** The scan
    used to page ``/events?active=false&closed=true`` by ``offset`` up to
    ``max_events = 100000``. Two measured facts made that structurally incapable
    of reaching a recent event:

    1. Gamma caps ``offset`` at 2000 (``offset=2100`` → HTTP 422 *"offset too
       large, use /events/keyset for deeper pagination"*), so the ceiling was
       unreachable by a factor of 50;
    2. with no ``order`` param Gamma serves **oldest-first**, so every run spent
       itself re-reading the same ~2,000 closed events from 2021.

    Nothing newer was ever marked resolved. 32,090 markets across 22,092 events
    were carried ``open`` while finished, some since 2020.

    Adding ``order="startDate", ascending=False`` — the fix #219E applied to the
    *active* scan — is the obvious repair and would have drained close to
    nothing: on ``closed=true`` the newest reachable 2,000 events span ~1.5 days
    and are essentially all hourly crypto, which ingest skips.

    So the population is taken from **our own rows** instead. Every unresolved
    Polymarket market yields a Gamma event id under
    :data:`GAMMA_EVENT_ID_EXPR` (measured: all 40,004 of them, 22,092 distinct),
    and ``/events?id=`` answers for any of them regardless of age — 9 of 9
    probed across 2020→2026 returned 200, closed ones included, because Gamma
    hides closed events from *list* endpoints only. The sweep is therefore
    bounded by our database rather than by Gamma's ordering, and no crypto flood
    can crowd it out. ~22k ids at 100 per request is ~221 calls, so a run
    normally covers the whole population; the cursor exists for the run that
    does not.

    **What may be resolved is decided per leg, by the venue** — see
    :func:`settled_legs`. A paged ``closed=true`` scan could take every condition
    id it saw because the filter had vouched for them; a direct fetch has no
    filter and returns live markets beside settled ones. Never by staleness: 407
    of 779 sampled stuck rows are long-horizon futures ("Illinois Senate Election
    Winner", ends 2026-11-03) that are legitimately open, and an age rule would
    resolve every one of them.
    """
    import asyncio
    import time as _time
    from app.services.polymarket_api import PolymarketAPIService

    import json as json_module

    import httpx

    from app.utils.polymarket_settlement_scan import (
        GAMMA_EVENT_ID_EXPR,
        GAMMA_MAX_IDS_PER_REQUEST,
        STALE_OPEN_AGE_HOURS,
        settled_legs,
    )
    from app.utils.resolved_write_gate import (
        PROOF_WINNER,
        REASON_CLOSED_WITHOUT_TERMINAL_PRICE,
        gate_stamp,
    )

    _json_dumps = json_module.dumps

    #: Wall budget for the id sweep. The Celery task's soft limit is 900s; this
    #: leaves room for the closing census and the return trip.
    _TIME_BUDGET_S = 600.0
    _deadline = _time.monotonic() + _TIME_BUDGET_S

    #: #6919. Path-door recoveries allowed per run — one HTTP call each, against
    #: a walk that already saturates its wall budget (`swept_full_population`
    #: read false on 2026-09-18 with 4,000 of 18,692 events swept). The refused
    #: population measured 26 ids in a 12,700-id run, so this is ~4x headroom
    #: over the observed rate and still a hard stop if that rate ever changes.
    #: Exhausting it is not silent: the remainder lands in
    #: `events_path_door_unattempted` and the next run's cursor walks past them
    #: again, which is exactly the state this counter exists to make visible.
    _PATH_DOOR_MAX_PER_RUN = 100
    _path_door_budget = _PATH_DOOR_MAX_PER_RUN

    stats = {
        "events_requested": 0,
        "events_returned": 0,
        # Requested ids Gamma did not answer for. A real signal now, and only
        # now: `get_events_by_ids` sends an explicit `limit`, so a short page no
        # longer means "the batch was silently truncated" (gotcha #53).
        #
        # #6919: it is still not the VENUE's absence. It is the LIST door's, and
        # the path door answers for the same id — see the recovery arm below.
        # The three counters that follow PARTITION this one:
        # `events_not_found` == recovered_via_path_door + absent_at_path_door
        #                       + path_door_unattempted (+ any id whose retry
        #                       errored, which lands in `errors`).
        "events_not_found": 0,
        # Ids the list door refused and `/events/{id}` answered for. This is the
        # population that was previously unreachable by this task at any cadence.
        "events_recovered_via_path_door": 0,
        # Ids BOTH doors refused — a genuine 404. "The venue does not know this
        # id" and "we asked the wrong door" are different findings and must
        # never share a counter (gotcha #53), which is the whole reason this
        # arm exists at all.
        "events_absent_at_path_door": 0,
        # Refused ids the recovery arm never got to, because the per-run cap or
        # the wall deadline stopped it. A non-zero value here means the run's
        # `events_absent_at_path_door` is a floor, not a census.
        "events_path_door_unattempted": 0,
        # Events Gamma returned with every leg still trading. Not a failure —
        # the long-horizon-futures class — but it must be visible, because a run
        # where this is the whole population resolved nothing for a good reason
        # and a run where it is zero resolved nothing for a bad one.
        "events_fully_open": 0,
        "settled_legs_seen": 0,
        # CERT-751 repair. Legs the venue still reports trading, and the markets
        # withheld because they carry one. `markets_held_mixed_children` is the
        # number this sweep DELIBERATELY did not resolve — a parent whose event
        # is partly settled and partly live. Counted rather than inferred,
        # because "resolved fewer than I expected" and "correctly refused a
        # still-trading parent" are the same rowcount otherwise (gotcha #53).
        "open_legs_seen": 0,
        "markets_held_mixed_children": 0,
        "markets_resolved": 0,
        "outcomes_updated": 0,
        # CAL-P086A: the resolves this task made with no winner to write. Kept
        # beside `markets_resolved` rather than folded into it — a run that
        # resolves 5,000 markets and grades none must not report the same
        # headline as one that graded them all.
        "resolved_without_winner_proof": 0,
        "swept_full_population": False,
        "errors": [],
    }

    async with get_task_session() as session:
        open_count = await session.execute(
            text("""
                SELECT COUNT(*) FROM futures_markets
                WHERE source = 'polymarket' AND status != 'resolved'
            """)
        )
        total_open = open_count.scalar()
        if total_open == 0:
            logger.info("Polymarket status sync: no open markets, skipping")
            return {**stats, "skipped": True}
        stats["unresolved_before"] = total_open

        # The needle, taken before the sweep so the run's own effect on it is
        # readable rather than inferred.
        stats["stale_open_before"] = (
            await session.execute(
                text("""
                    SELECT count(*) FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.commence_time
                          < now() - make_interval(hours => :stale_hours)
                """),
                {"stale_hours": STALE_OPEN_AGE_HOURS},
            )
        ).scalar()

    service = PolymarketAPIService()
    try:
        from app.tasks.redis_state import get_redis_client
        _rc = get_redis_client()

        # The offset cursor the old scan carried is meaningless to this one, and
        # a stale key that still parses is worse than no key. Dropped once, here,
        # rather than left for a future reader to interpret.
        _rc.delete("bainluck:polymarket_sync_offset")

        _cursor_key = "bainluck:polymarket_resolved_sync:cursor"
        try:
            cursor = int(_rc.get(_cursor_key) or 0)
        except (TypeError, ValueError):
            cursor = 0

        # The whole population, read ONCE, ascending by id.
        #
        # Not re-queried per batch, and the difference is the run: the DISTINCT
        # over the 40k unresolved rows costs ~1.5s, and paying it 221 times
        # would spend more wall clock on bookkeeping than on Gamma. 22k numeric
        # strings is ~1.5 MB of plain data held in a local — never ORM rows,
        # which do not survive the commit boundaries below (gotcha #6).
        #
        # Ascending id is a stable total order over the exact population, so
        # every id is visited before any is revisited — the property gotcha #41
        # is actually about. Neither end starves: rows leave the set as they
        # resolve, and the cursor wraps at the tail. `::bigint` is safe because
        # all 22,092 ids are numeric (measured); the regex keeps it that way if
        # that ever stops being true.
        async with get_task_session() as session:
            all_ids = [
                row[0]
                for row in (
                    await session.execute(
                        # The DISTINCT is INSIDE and the ORDER BY is outside,
                        # and it has to be that way round: under
                        # `SELECT DISTINCT`, Postgres requires every ORDER BY
                        # expression to appear in the select list, so
                        # `SELECT DISTINCT eid ... ORDER BY eid::bigint` is not
                        # a slow query, it is a syntax error — one that this
                        # task's broad `except` would have swallowed into a
                        # `task_error` and reported as a run that drained
                        # nothing. Verified against production 2026-09-02.
                        text(f"""
                            SELECT eid FROM (
                                SELECT DISTINCT {GAMMA_EVENT_ID_EXPR} AS eid
                                  FROM futures_markets fm
                                 WHERE fm.source = 'polymarket'
                                   AND fm.status != 'resolved'
                            ) s
                            WHERE eid ~ '^[0-9]+$'
                            ORDER BY eid::bigint
                        """)
                    )
                ).fetchall()
            ]
        stats["population_events"] = len(all_ids)

        # --- the recency head (#6734, measured 2026-09-18) -------------------
        #
        # The ascending cursor above is fair, and on its own it does not finish.
        # Measured on production across the four runs of 2026-09-17: the sweep
        # covers ~57% of the population inside its 600s and stops around event
        # id 1.01M, while the population runs to 1.04M — 7,486 of 17,560 events
        # above the 23:30Z stopping point. Three of those four runs started from
        # the BOTTOM of the range (a run that reaches the tail wraps the cursor
        # to 0, so the next one begins again at the oldest id) and none of the
        # three climbed back to the top before the budget ran out.
        #
        # Event ids ascend with creation, so the unreached band is exactly where
        # events that closed TODAY live. That is gotcha #41's second clause: an
        # oldest-first walk over a population whose interesting rows are the
        # newest needs BOTH bounds. The cost was measurable on the page — a
        # sub-market the venue closed and resolved 7.5h earlier still served
        # `probability 1.0, is_winner null` beneath its own graded mirror
        # (market 61262638, #6734) — and it compounds, because `clob_resolve`
        # selects `status = 'resolved'`, so a row stranded at `open` can never
        # acquire the verdict that would make it render correctly.
        #
        # So the newest slice gets a guaranteed share of the wall clock FIRST,
        # and the backlog keeps the rest of it. Both bounds, neither starved.
        #
        # This changes only WHICH ids reach the resolver first. `settled_legs`,
        # the UPDATE and the CERT-751 mixed-children guard are untouched, so the
        # head cannot resolve anything the cursor would not have resolved on
        # reaching it — it only reaches it sooner. Head batches are also the
        # cheap ones: recent events are mostly still trading, so they return
        # `events_fully_open` and write nothing.
        #
        # Sized from the same measurement, not from taste: ~5.4s per 100-event
        # batch observed, so 4,000 events is ~40 batches ~ 216s, inside the
        # head's 240s. The head never advances the cursor — the backlog's
        # progress is the cursor's own, and letting the head jump it would skip
        # the very rows the cursor is walking towards.
        _HEAD_EVENTS = 4000
        _HEAD_BUDGET_S = 240.0

        # Newest FIRST inside the head, which is the opposite of the walk below
        # and is the point of it. If the head budget truncates, what it drops
        # has to be the head's OLDER end — those ids are the ones the ascending
        # cursor is closest to reaching on its own. Dropping the fresh end would
        # re-create the defect inside the arm built to fix it.
        head = list(reversed(all_ids[-_HEAD_EVENTS:]))
        head_set = set(head)
        tail = [eid for eid in all_ids if int(eid) > cursor and eid not in head_set]
        if not tail and cursor:
            # Resuming past the tail — the population shrank under the cursor.
            # Wrap immediately rather than reporting an empty sweep.
            _rc.delete(_cursor_key)
            cursor = 0
            tail = [eid for eid in all_ids if eid not in head_set]

        pending = head + tail
        _head_remaining = len(head)
        _head_deadline = _time.monotonic() + _HEAD_BUDGET_S
        stats["head_events"] = len(head)
        stats["head_events_swept"] = 0
        # Head ids the head budget did not reach. Distinct from `head_events` -
        # "the head swept clean" and "the head ran out of time" are different
        # runs and must not return the same shape (gotcha #53).
        stats["head_events_skipped"] = 0

        while True:
            if _time.monotonic() >= _deadline:
                logger.info(
                    "Polymarket status sync: time budget reached, cursor at %s",
                    cursor,
                )
                break

            in_head = _head_remaining > 0
            if in_head and _time.monotonic() >= _head_deadline:
                # Head budget spent. Drop what is left of it and hand the rest
                # of the wall clock to the cursor, which is the half that must
                # not be starved by this arm.
                stats["head_events_skipped"] = _head_remaining
                pending = pending[_head_remaining:]
                _head_remaining = 0
                in_head = False

            # A batch never straddles the two arms: while the head is draining,
            # the take is clamped to what is left of it. That is what keeps
            # "did this batch advance the cursor" a property of the batch rather
            # than of the ids inside it.
            take = min(GAMMA_MAX_IDS_PER_REQUEST, _head_remaining) if in_head \
                else GAMMA_MAX_IDS_PER_REQUEST
            batch_ids = pending[:take]
            pending = pending[take:]
            if in_head:
                _head_remaining -= len(batch_ids)
                stats["head_events_swept"] += len(batch_ids)

            if not batch_ids:
                # The tail. Wrap so the next run starts from the oldest id
                # again, and say so — "swept the whole population and found
                # nothing left to resolve" and "gave up early" are different
                # runs and must not return the same shape.
                _rc.delete(_cursor_key)
                stats["swept_full_population"] = True
                break

            stats["events_requested"] += len(batch_ids)

            try:
                raw_events = await service.get_events_by_ids(batch_ids)
            except httpx.HTTPStatusError as e:
                # 429 keeps the cursor so the next run resumes here; never
                # swallowed into a generic skip (gotcha #36).
                if e.response.status_code == 429:
                    stats["errors"].append(f"rate_limited at cursor {cursor}")
                    logger.warning(
                        "Polymarket status sync: 429 at cursor %s, stopping",
                        cursor,
                    )
                    break
                stats["errors"].append(
                    f"batch at cursor {cursor}: HTTP {e.response.status_code}"
                )
                break
            except Exception as e:
                # One bad batch must not wipe the run (gotcha #42) — advance
                # past it and keep going. A HEAD batch is already consumed from
                # `pending`, so it is skipped either way; what it must not do is
                # move the cursor, which belongs to the ascending walk alone.
                stats["errors"].append(f"batch at cursor {cursor}: {e}")
                if not in_head:
                    cursor = int(batch_ids[-1])
                    _rc.setex(_cursor_key, 86400 * 7, str(cursor))
                await asyncio.sleep(0.3)
                continue

            stats["events_returned"] += len(raw_events)
            stats["events_not_found"] += len(batch_ids) - len(raw_events)

            # --- #6919: the refused ids, re-asked at the door that answers ---
            #
            # MEASURED 2026-09-18 against live Gamma. `/events?id=744619` returns
            # `[]` — bare, with `active=false`, and with `closed=true&active=false`
            # — while `/events/744619` returns 200 with the full nested payload,
            # `closed: true`, and four legs quoting terminal prices. Same for
            # 792826. So an id in `events_not_found` above is not an id the venue
            # has forgotten; it is an id we asked the wrong door about, and for
            # the markets behind it this task is not slow, it is BLIND — no
            # cadence, no budget and no cursor position can ever reach them.
            #
            # The cost of the blindness, measured the same morning: of eighteen
            # wholly-settled Polymarket markets still carried `open`, eleven
            # drained inside a single run of this task and the remaining SEVEN
            # were exactly the markets of those two events — including the four
            # "Will there be N hurricanes during the Atlantic Hurricane Season in
            # 2026?" questions a reader still meets on search, priced "No 100%",
            # 51 days after the venue closed the book.
            #
            # `settled_legs` accepts the path payload unchanged (verified on both
            # specimens: 744619 -> 4 settled / 0 open, 792826 -> 14 settled / 7
            # open), so recovered events join `raw_events` and every downstream
            # rule — the per-leg closed test, the mixed-children guard, the
            # winner-proof split — applies to them exactly as written.
            #
            # Bounded three ways, because this arm is one HTTP call per id and
            # the batch walk is already wall-limited: a per-run cap, the same
            # `_deadline` the walk yields to, and a 429 that stops the arm for
            # the rest of the run rather than spending the budget on refusals.
            # What it never does is guess: an id both doors refuse is a genuine
            # absence and is counted as one.
            _missing = [
                eid for eid in batch_ids
                if str(eid) not in {str(r.get("id")) for r in raw_events}
            ]
            for _eid in _missing:
                if _path_door_budget <= 0 or _time.monotonic() >= _deadline:
                    stats["events_path_door_unattempted"] += 1
                    continue
                _path_door_budget -= 1
                try:
                    _recovered = await service.get_event_by_id(str(_eid))
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # Spend nothing further on a door that is refusing us;
                        # the batch walk keeps its own 429 handling above.
                        stats["errors"].append(
                            f"path door rate_limited at event {_eid}"
                        )
                        _path_door_budget = 0
                        continue
                    stats["errors"].append(
                        f"path door event {_eid}: HTTP {e.response.status_code}"
                    )
                    continue
                except Exception as e:  # one bad id never wipes the run (#42)
                    stats["errors"].append(f"path door event {_eid}: {e}")
                    continue
                if _recovered is None:
                    stats["events_absent_at_path_door"] += 1
                    continue
                stats["events_recovered_via_path_door"] += 1
                raw_events = [*raw_events, _recovered]

            # --- what the venue says is over, leg by leg --------------------
            settled_cids: list[str] = []
            settlement_prices: dict[str, tuple[float, float | None]] = {}
            terminal_cids: list[str] = []
            # CERT-751 repair. Every leg the venue still reports TRADING, kept
            # for the mixed-children guard below. Collected for EVERY event,
            # including fully-open ones and before the `continue` — resolution
            # is a one-way write, so the guard fails closed: a condition id seen
            # open anywhere in this batch withholds the market that carries it.
            open_cids: list[str] = []
            for raw in raw_events:
                legs = settled_legs(raw)
                if legs is None:
                    continue
                open_cids.extend(legs.open_condition_ids)
                if not legs.settled_condition_ids:
                    stats["events_fully_open"] += 1
                    continue
                settled_cids.extend(legs.settled_condition_ids)
                settlement_prices.update(legs.settlement_prices)
                terminal_cids.extend(legs.terminal_condition_ids)
            stats["settled_legs_seen"] += len(settled_cids)
            stats["open_legs_seen"] += len(open_cids)

            if settled_cids:
                # Also include _yes/_no suffixed external_ids for sub-market
                # outcome matching and condition_ids as market external_ids
                # for sub-market FuturesMarket status resolution.
                extended_cids = list(settled_cids)
                for cid in settled_cids:
                    extended_cids.append(f"{cid}_yes")
                    extended_cids.append(f"{cid}_no")

                # CAL-P086A (`C-WINNER-WRITER-1` [P0]). A closed Polymarket
                # market does NOT imply a readable winner: codex's specimen is a
                # closed market quoting 0.60/0.40, which used to come through
                # here as `markets_resolved: 1, outcomes_updated: 0` — resolved,
                # ungraded, and indistinguishable in the database from a market
                # where everyone genuinely lost.
                #
                # Which rows have proof is already known at this point: it is
                # exactly the terminal envelope the winner writes below use. So
                # the stamp splits by that same test rather than a second one,
                # and each row records its own basis.
                _terminal_extended = list(terminal_cids)
                for cid in terminal_cids:
                    _terminal_extended.append(f"{cid}_yes")
                    _terminal_extended.append(f"{cid}_no")

                # CERT-751 repair. The still-trading legs, under the same
                # `_yes`/`_no` widening the settled side uses — a decomposed
                # sub-market stores its legs suffixed, so a guard that matched
                # only the bare condition id would miss exactly the decomposed
                # parents this exists to protect.
                _open_extended = list(open_cids)
                for cid in open_cids:
                    _open_extended.append(f"{cid}_yes")
                    _open_extended.append(f"{cid}_no")

                _proof_stamp = _json_dumps(
                    gate_stamp(
                        task="sync_polymarket_resolved_status",
                        proof_kind=PROOF_WINNER,
                    )
                )
                _reason_stamp = _json_dumps(
                    gate_stamp(
                        task="sync_polymarket_resolved_status",
                        reason=REASON_CLOSED_WITHOUT_TERMINAL_PRICE,
                    )
                )

                async with get_task_session() as session:
                    # Resolve parent markets via outcome external_id match.
                    # The CASE writes each row's own basis; CAST(:p AS jsonb)
                    # rather than `:p::jsonb`, because asyncpg drops a bind that
                    # is immediately followed by a `::` cast (standing gotcha).
                    result = await session.execute(
                        text("""
                            UPDATE futures_markets
                            SET status = 'resolved',
                                settled_at = COALESCE(settled_at, NOW()),
                                market_metadata =
                                    COALESCE(market_metadata, '{}'::jsonb)
                                    || CASE WHEN (
                                           id IN (
                                               SELECT fo.market_id
                                               FROM futures_outcomes fo
                                               WHERE fo.external_id
                                                     = ANY(:terminal_cids)
                                           )
                                           OR external_id = ANY(:terminal_raw)
                                       )
                                       THEN CAST(:proof_stamp AS jsonb)
                                       ELSE CAST(:reason_stamp AS jsonb)
                                       END
                            WHERE source = 'polymarket'
                              AND status != 'resolved'
                              AND (
                                  id IN (
                                      SELECT fo.market_id
                                      FROM futures_outcomes fo
                                      WHERE fo.external_id = ANY(:cids)
                                  )
                                  OR external_id = ANY(:raw_cids)
                              )
                              -- CERT-751 repair: the parent+mixed-children
                              -- guard. One settled leg used to be enough to
                              -- resolve the market that carries it, so a
                              -- `polymarket_event` parent aggregating 50 legs
                              -- was marked resolved on the strength of one --
                              -- the grader's specimen is Gamma event 92611,
                              -- 24 legs closed and 26 STILL TRADING, whose
                              -- production parent 113566 holds both. That
                              -- pulls a live 50-outcome market off every open
                              -- surface. A market is resolvable only when NONE
                              -- of its legs is still trading; the settled
                              -- children of a mixed event still resolve
                              -- individually, which is the half of #2637 that
                              -- was always correct.
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM futures_outcomes fo_open
                                  WHERE fo_open.market_id = futures_markets.id
                                    AND fo_open.external_id = ANY(:open_cids)
                              )
                              AND NOT (external_id = ANY(:open_raw))
                        """),
                        {
                            "cids": extended_cids,
                            "raw_cids": settled_cids,
                            "terminal_cids": _terminal_extended,
                            "terminal_raw": terminal_cids,
                            "open_cids": _open_extended,
                            "open_raw": open_cids,
                            "proof_stamp": _proof_stamp,
                            "reason_stamp": _reason_stamp,
                        },
                    )
                    page_resolved = result.rowcount

                    # CERT-751 repair, the counted half. What the guard above
                    # WITHHELD: rows the old predicate would have resolved that
                    # carry a still-trading leg. Without this the repair is
                    # invisible — a sweep that correctly refuses a live parent
                    # and a sweep that simply found nothing report the same
                    # `markets_resolved`, and the next reader cannot tell a
                    # working guard from a dead one.
                    held = await session.execute(
                        text("""
                            SELECT COUNT(*)
                            FROM futures_markets
                            WHERE source = 'polymarket'
                              AND status != 'resolved'
                              AND (
                                  id IN (
                                      SELECT fo.market_id
                                      FROM futures_outcomes fo
                                      WHERE fo.external_id = ANY(:cids)
                                  )
                                  OR external_id = ANY(:raw_cids)
                              )
                              AND (
                                  EXISTS (
                                      SELECT 1
                                      FROM futures_outcomes fo_open
                                      WHERE fo_open.market_id = futures_markets.id
                                        AND fo_open.external_id = ANY(:open_cids)
                                  )
                                  OR external_id = ANY(:open_raw)
                              )
                        """),
                        {
                            "cids": extended_cids,
                            "raw_cids": settled_cids,
                            "open_cids": _open_extended,
                            "open_raw": open_cids,
                        },
                    )
                    stats["markets_held_mixed_children"] += held.scalar() or 0

                    # How many of this batch's settled legs had no winner to
                    # write. A count, not an estimate: it is the legs the CASE
                    # sent down the reason branch. Reported so a run that
                    # resolves thousands of ungradeable markets cannot read the
                    # same as one that settled them (gotcha #53).
                    _terminal_set = set(terminal_cids)
                    stats["resolved_without_winner_proof"] += len(
                        [cid for cid in settled_cids if cid not in _terminal_set]
                    )

                    # Batch update settlement prices + set is_winner + resolution_source.
                    # All settlement prices with yes_price >= 0.95 are winners;
                    # all with yes_price <= 0.05 are losers.
                    page_outcomes_updated = 0
                    winner_cids = []
                    loser_cids = []
                    for cid in terminal_cids:
                        yes_price, _no_price = settlement_prices[cid]
                        if yes_price >= 0.95:
                            winner_cids.extend([cid, f"{cid}_yes"])
                            loser_cids.append(f"{cid}_no")
                        elif yes_price <= 0.05:
                            loser_cids.extend([cid, f"{cid}_yes"])
                            winner_cids.append(f"{cid}_no")

                    # Q487: these WHERE clauses key on `external_id` alone, and
                    # `futures_outcomes.external_id` is NOT unique — one condition
                    # can sit on two markets under two conventions. Measured on
                    # production: `0xeda9…e084_yes` and `…_no` each exist on BOTH
                    # container_member 13798072 ("Will Zoë Kravitz be one of Taylor
                    # Swift's bridesmaids?", where they are the real outcomes) AND
                    # field market 12194657 ("Who will Taylor Swift's bridesmaids
                    # be?", where they are duplicates of the bare `…e084` Zoë row).
                    # One settlement writes all of them. On the field market that
                    # crowns a bare "No" over ten named people — and unlike
                    # `clean_resolution`, `api_settlement` IS calibration-truth
                    # eligible, so the wrong grade reaches the published curve.
                    # Scoped by the shared duplicate-leg rule, not by market id:
                    # the container_member rows are the legitimate target and must
                    # keep being written.
                    # #7767 — THE SKIP TESTS THE SETTLEMENT, NOT ITS STAMP.
                    #
                    # These two statements already wrote the right price; what
                    # they could not do was REVISIT a leg. The guard here was
                    # `COALESCE(fo.resolution_source,'') != 'api_settlement'`,
                    # which keys the skip on the one column a half-finished
                    # settlement already has right — so a leg that reached
                    # `api_settlement` by any other route kept whatever price it
                    # was carrying, permanently, and this rail (the only one that
                    # reads `outcomePrices` on an OPEN board) was sealed out of it.
                    #
                    # WHAT A READER SAW. `/futures/113360` — "How many different
                    # countries will Israel strike in 2026?" — printed **100%** in
                    # the board's largest type for leg `0`, beside "4" at 76%, and
                    # drew it as a flat green line at 100% all week. Gamma has that
                    # leg `closed: true`, `umaResolutionStatus: resolved`,
                    # `outcomePrices: ["0","1"]` — resolved NO — while its
                    # `lastTradePrice` sits at `1` against a `0.001` ask, which is
                    # where the stored number came from. We held the verdict
                    # (`is_winner=false`, `api_settlement`) and published over it.
                    #
                    # REACH, executed rather than reasoned (Gamma event 79926 run
                    # through `settled_legs` on 2026-09-21): all four graded legs
                    # of that board are in `terminal_condition_ids`, and the
                    # specimen's `settlement_prices` entry is `(0.0, 1.0)` — so it
                    # is in `loser_cids` on every run and was refused by the guard
                    # alone. 217 legs on 96 open boards are in this state.
                    #
                    # Idempotence is kept, and by a stricter test than before: a
                    # row whose grade, side and price already match is still
                    # skipped, so the steady state writes nothing. `IS DISTINCT
                    # FROM` rather than `!=` because both columns are nullable.
                    #
                    # #6110 IS OBEYED IN BOTH DIRECTIONS. The winner statement
                    # writes 1.0 over a settled champion carrying a losing price
                    # for exactly the same reason, so this preserves a crowned leg
                    # rather than only declining to delete it.
                    #
                    # 🔴 AND THIS NEVER WRITES ON THE STRENGTH OF OUR OWN GRADE,
                    # which is what makes re-touching a graded row safe. Both cid
                    # lists are built above from `terminal_cids` + the
                    # `settlement_prices` this pass just read off Gamma, so a row
                    # is written only where the VENUE's current `outcomePrices`
                    # are terminal for that condition. `resolution_source` enters
                    # the statement in one place only — the skip — where it
                    # decides whether the write is still NEEDED, never whether it
                    # is WARRANTED. A leg carrying a fabricated grade (#3617's
                    # class) is therefore not zeroed by this: it is written only
                    # if Gamma also says the contract is over.
                    if winner_cids:
                        r_w = await session.execute(
                            settle_outcomes_stmt(SETTLED_YES_PRICE, "true"),
                            {"cids": winner_cids},
                        )
                        page_outcomes_updated += r_w.rowcount

                    if loser_cids:
                        r_l = await session.execute(
                            settle_outcomes_stmt(SETTLED_NO_PRICE, "false"),
                            {"cids": loser_cids},
                        )
                        page_outcomes_updated += r_l.rowcount

                    if page_resolved > 0 or page_outcomes_updated > 0:
                        await session.commit()
                        stats["markets_resolved"] += page_resolved
                        stats["outcomes_updated"] += page_outcomes_updated

            # Advance past this batch whatever happened to it. A batch that
            # resolved nothing is still swept — the old `zero_update_pages`
            # counter existed to escape an offset walk that could not move, and
            # a keyset cursor over our own rows has no such trap.
            #
            # The head arm is deliberately outside this. Its ids are the highest
            # in the population, so writing one into the cursor would jump the
            # ascending walk past every id it has not visited yet — the backlog
            # would be declared swept without being read.
            if not in_head:
                cursor = int(batch_ids[-1])
                _rc.setex(_cursor_key, 86400 * 7, str(cursor))
            await asyncio.sleep(0.1)

            if stats["events_requested"] % 5000 == 0:
                logger.info(
                    "Polymarket status sync: %d events, %d resolved, %d outcomes updated",
                    stats["events_requested"], stats["markets_resolved"],
                    stats["outcomes_updated"],
                )

    except Exception as e:
        stats["errors"].append(f"task_error: {str(e)[:200]}")
    finally:
        await service.close()

    # The needle again, after. Both ends are recorded because the drop is the
    # only thing that proves the run did anything to the class #2637 named, and
    # a run that resolves markets outside that class must not read as progress
    # against it.
    try:
        async with get_task_session() as session:
            stats["stale_open_after"] = (
                await session.execute(
                    text("""
                        SELECT count(*) FROM futures_markets fm
                        WHERE fm.source = 'polymarket'
                          AND fm.status = 'open'
                          AND fm.commence_time
                              < now() - make_interval(hours => :stale_hours)
                    """),
                    {"stale_hours": STALE_OPEN_AGE_HOURS},
                )
            ).scalar()
    except Exception as e:
        stats["errors"].append(f"census_after: {str(e)[:120]}")

    # Publish the run for the #2637 needle
    # (`GET /api/admin/polymarket/stale-open`). The census there can count the
    # class but cannot tell an open market from a finished one — only this sweep
    # asked the venue, so only this sweep can say how much of the class is real.
    try:
        from app.tasks.redis_state import get_redis_client
        from app.utils.polymarket_settlement_scan import SYNC_SUMMARY_KEY

        get_redis_client().setex(
            SYNC_SUMMARY_KEY,
            86400 * 7,
            json_module.dumps(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    **{
                        k: v
                        for k, v in stats.items()
                        if k != "errors"
                    },
                    "errors": stats["errors"][:5],
                },
                default=str,
            ),
        )
    except Exception as e:
        stats["errors"].append(f"summary_publish: {str(e)[:120]}")

    logger.info(
        "Polymarket status sync: %d events requested, %d returned, %d not found, "
        "%d markets resolved, %d outcomes updated, stale-open %s -> %s",
        stats["events_requested"], stats["events_returned"],
        stats["events_not_found"], stats["markets_resolved"],
        stats["outcomes_updated"], stats.get("stale_open_before"),
        stats.get("stale_open_after"),
    )
    return stats


async def _backfill_polymarket_volume(max_pages: int = 200):
    """Backfill per-outcome volume for Polymarket from the Gamma API.

    ⚠️ **SUPERSEDED AND NEVER WIRED — do not schedule this. See
    ``app/tasks/repair_polymarket_evidence.py`` (#1870, CAL-P060).**

    Three things measured on 2026-08-14 that this docstring previously asserted
    the opposite of. They are recorded here rather than in a commit message
    because the next person to find this function will read the docstring:

    1. **It has no caller.** No Celery task, no beat entry, no route. Its only
       reference outside this ``def`` is a test that reads its SOURCE TEXT with
       ``inspect.getsource`` and asserts substrings appear in it. Every one of
       those assertions passes on a function that has never executed. The 28.6%
       of Polymarket outcomes that do carry volume come from forward capture in
       ``_process_event_batch``, not from here.
    2. **``order="volume", ascending=False`` does not sort by volume.** It is a
       LEXICOGRAPHIC sort on the volume string. Measured first page:
       ``99.99999999999999``, ``999.96``, ``99.996``, ``9.999343``. So "the
       meaningful-volume markets are filled before the long tail" is false — a
       $12M market sorts under ``1`` and lands near the end, and a market with
       volume ``0`` sorts last of all. That is why Polymarket has exactly 0.00%
       confirmed-zero rows: they are the last rows this would ever reach.
    3. **``offset`` caps at 2000** (2000 → 200, 2050 → 422). Total addressable
       population ~2,100 markets, forever; the ``wrapped`` branch below can
       never fire. Against a NULL cohort in the tens of thousands the pager is
       not slow, it is bounded away from the answer.

    Kept, not deleted, because the census that measures the hole still reasons
    about what filled the 28.6% — and because a deleted function cannot warn
    anyone. The original description follows, with its false claim struck:

    Polymarket polling stored only event-level AGGREGATE volume; per-outcome
    (per-condition) volume was never written, so ~all resolved Polymarket
    outcomes have NULL ``volume`` — which blocks the traded/untraded
    calibration tag for that source. This pages CLOSED markets from Gamma
    (each carries ``conditionId`` + ``volume``) in what it BELIEVES is
    high-volume-first order (see 2 above — it is not) and bulk-updates
    ``fo.volume`` keyed on condition_id / _yes / _no.

    VP-efficient + queue-safe: bulk set-based writes (one ``UPDATE ... FROM
    unnest`` per page, not per row), Redis offset cursor (resumable),
    time-boxed at 480s, 429-backoff, write-on-change. Run OUT-OF-BAND (its own
    dyno / low-priority queue) — never contend with live polling. Gotchas: #6
    (commit per batch), #899 (no broad in-memory pull), #36 (don't catch-all —
    distinguish 429 from real errors). fo.volume is an Integer column, so cap
    at ~2B to avoid overflow on the handful of multi-billion-dollar markets
    (the magnitude beyond that is irrelevant to a traded/threshold tag).
    """
    import asyncio
    import time as _time
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.redis_state import get_redis_client

    stats = {"pages": 0, "markets": 0, "rows_updated": 0, "wrapped": False, "errors": []}
    _CAP = 2_000_000_000

    _rc = get_redis_client()
    cursor_key = "bainluck:poly_volume_backfill"
    offset = int(_rc.get(cursor_key) or 0)
    svc = PolymarketAPIService()
    _start = _time.monotonic()

    try:
        for _ in range(max_pages):
            if (_time.monotonic() - _start) > 480:
                break
            try:
                markets = await svc.get_markets(
                    active=None, closed=True, limit=100, offset=offset,
                    order="volume", ascending=False,
                )
            except Exception as e:
                if "429" in str(e):
                    await asyncio.sleep(5)
                    continue
                stats["errors"].append(str(e)[:200])
                break

            if not markets:
                # Reached the end — reset cursor so a later run restarts and
                # picks up newly-resolved markets.
                _rc.delete(cursor_key)
                stats["wrapped"] = True
                break

            offset += len(markets)
            _rc.setex(cursor_key, 86400 * 7, str(offset))
            stats["pages"] += 1

            cids, vols = [], []
            for m in markets:
                cid = m.get("conditionId") or m.get("condition_id")
                vraw = m.get("volume")
                if vraw is None:
                    vraw = m.get("volumeNum")
                if cid and vraw is not None:
                    try:
                        cids.append(cid)
                        vols.append(min(int(float(vraw)), _CAP))
                    except (ValueError, TypeError):
                        pass

            if not cids:
                continue
            stats["markets"] += len(cids)

            async with get_task_session() as session:
                r = await session.execute(
                    text("""
                        UPDATE futures_outcomes fo
                        SET volume = v.vol, last_updated = NOW()
                        FROM unnest(CAST(:cids AS text[]), CAST(:vols AS bigint[])) AS v(cid, vol)
                        WHERE fo.external_id IN (v.cid, v.cid || '_yes', v.cid || '_no')
                          AND fo.volume IS DISTINCT FROM v.vol
                    """),
                    {"cids": cids, "vols": vols},
                )
                stats["rows_updated"] += r.rowcount
                await session.commit()

        logger.info(
            "Polymarket volume backfill: %d pages, %d markets, %d rows updated (wrapped=%s, %d errors)",
            stats["pages"], stats["markets"], stats["rows_updated"],
            stats["wrapped"], len(stats["errors"]),
        )
    except Exception as e:
        stats["errors"].append(str(e)[:200])
        logger.error("Polymarket volume backfill error: %s", e)

    return stats
