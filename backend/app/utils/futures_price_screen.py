"""Read-side futures price screens for detail, feed, and event concepts.

Keep this module independent of routes so concept adapters and cache warmers
can apply the same price rules without loading the API router.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
from app.utils.feed_market_quality import is_empty_book_midpoint
from app.utils.futures_unsupported_price import (
    MIDPOINT_TRADE_SOURCES,
    field_names_two_favourites,
    leg_has_no_live_support,
    market_is_proved_exclusive_field,
    midpoint_refuted_by_last_trade,
    needs_trade_disconfirmation,
    needs_trade_evidence,
    needs_unbacked_ask_evidence,
    price_is_an_unbacked_ask,
    price_is_an_unbacked_majority,
    price_is_unlocated_in_broken_field,
    price_is_unsupported,
    price_refuted_by_live_book,
    row_carries_a_verdict,
    unsupported_legs_above_the_supported_head,
)
from app.utils.kalshi_empty_book import KALSHI_BOOKMAKER

logger = logging.getLogger(__name__)




def _leg_prices_an_empty_book(outcome) -> bool:
    """Is this leg's number the midpoint of a book with nothing in it? (#6676)

    WHAT A READER SAW. Three consecutive Game Props cards in one 390px viewport
    on ``/sports``, each printing **Over 50% / Under 50%** with the bar drawn at
    exactly half, directly beneath a card whose 57/43 was real — so the reader
    had no way to tell a manufactured coin flip from a forecast. The stored rows
    behind them (outcomes 230498576, 230496527, 230475436, read 2026-09-17):
    ``current_probability 0.500000`` beside ``current_yes_bid 0.0200 /
    current_yes_ask 0.9700``, ``volume`` and ``price_changed_at`` both NULL. That
    quote bounds nothing, and its own midpoint is 0.495 — the stored number is
    half a cent off the book it was averaged from. A fabricated 50% is the one
    number that looks most like an answer.

    THE RULE IS NOT NEW AND IS NOT RE-DERIVED HERE. :func:`is_empty_book_midpoint`
    is #5247's shipped predicate, with its own measured constants, and the
    expression below is field for field the one already running at its call site
    in ``routes/events.py`` (``game-markets``). That surface got the rule and this
    one did not, which is the entire defect: the strip and the event page draw
    from the same rows and disagreed about whether those rows have a price. A
    second, differently-spelled copy of a price rule is exactly what
    ``futures_unsupported_price`` exists to prevent, so this is a delegation with
    a name, not a policy.

    IT IS A NAMED FUNCTION AND NOT AN INLINE COMPREHENSION for the reason
    :func:`_market_has_priced_outcome` states directly below: the one property
    that makes it a fix has to be testable without standing up the route.

    A LEG, NOT A MARKET, for the reason the shipped call site gives: a props
    market carries real lines beside its unpriced ones and dropping the card
    would take the real ones with it. A market whose legs are ALL empty-book then
    has no priced outcome left, and ``_market_has_priced_outcome`` drops its card
    BEFORE the truncation (#2710) — so the vacated slot is backfilled from the
    ``limit * 5`` rows the route already loaded and the strip stays a full strip.

    WHAT IT DELIBERATELY DOES NOT TOUCH. Read-side only (gotcha #21): nothing
    here rewrites a stored price, and withholding rather than rewriting is the
    standing rule, because ``calibration_probability`` coalesces to stored values
    (gotcha #144 / ruling 103) and an invented price becomes a forecast we are
    graded on. A genuine 50% on a tight book (49c/51c), a one-sided real ask and
    every model price (both book columns NULL) are all passed through by the
    predicate's own construction.

    🪤 "A TRADED 50% IS PASSED THROUGH" USED TO BE ON THAT LIST AND IT WAS WRONG.
    The #5333 bid-bound move (0.02 -> 0.05, 2026-09-17) made it measurable: of the
    1,119 rows it newly reaches, two are a genuinely traded 0.500 sitting on a
    now-empty 3c/97c book, and this function withdraws them. It cannot do
    otherwise — it reads three columns and the serve path carries no provenance of
    where a stored price came from. The writer's volume-gated last-trade exception
    protects the ingest side by SUBSTITUTING the trade price; nothing carries that
    label through to here. So the honest sentence for this surface is "no current
    quote supports this number", never "this number was never real".
    """
    # `getattr` RATHER THAN ATTRIBUTE ACCESS, matching `_book_refuted_outcome_ids`
    # below, and #6757 is why it changed. Until then this ran on exactly one call
    # site holding ORM rows, where the three columns always exist. It now also runs
    # on every `/api/futures/{id}` request, and a serve path must not 500 because a
    # caller handed it an object without a book — the absent case is "no book to
    # call empty", which falls through to the honest answer of leaving the price
    # alone. `is_empty_book_midpoint` already returns False for a null book, so this
    # is the same fail-open the predicate documents and not a second rule.
    return is_empty_book_midpoint(
        getattr(outcome, "current_probability", None),
        getattr(outcome, "current_yes_bid", None),
        getattr(outcome, "current_yes_ask", None),
    )


def _as_float(value) -> Optional[float]:
    """`Numeric` columns arrive as `Decimal`; the price predicates take floats.

    None-preserving on purpose: ``is_lone_ask_on_empty_book`` distinguishes a
    missing book from a zero bid, and coercing None to 0.0 here would hand it a
    bid nobody recorded and call it nobody bidding.
    """
    return None if value is None else float(value)


def _unsupported_price_candidates(market: FuturesMarket) -> list:
    """The legs of this market worth spending a trade read on (#7632 split).

    THE SCREEN, LIFTED OUT OF THE ARM SO TWO CALLERS SHARE ONE SPELLING. The
    page asks this market-by-market; the feed's snapshot builder asks it of
    every candidate board at once so it can issue ONE trade query for the whole
    pool instead of one per board. Both reach the same rows because both call
    THIS — the alternative is a second copy of the screen, which is precisely
    what `_withheld_price_outcome_ids`'s "ONE HELPER, NOT A FIFTH SPELLING"
    forbids. Nothing about the rule moved; only the fetch did.
    """
    # `getattr` for the same reason the outcome reads below use it: a caller may
    # hand this a market object that never loaded these columns, and an absent
    # attribute must read as "not proved" rather than raise or, worse, be taken
    # for evidence. The gate fails closed on None, so the leg is served.
    in_exclusive_field = market_is_proved_exclusive_field(
        getattr(market, "market_type", None),
        getattr(market, "market_metadata", None),
    )
    # 🔴 #7747 — A SECOND ARM SHARES THIS CANDIDATE LIST AND THIS SNAPSHOT READ.
    # `price_is_an_unbacked_ask` asks a different question of the same three
    # columns (does the book LOCATE the price, not does it REFUTE it) and needs
    # the same one thing from the snapshot table: the newest Kalshi trade. It is
    # unioned in here rather than given its own `_..._outcome_ids` helper so the
    # page still issues ONE trade query per market — the arm adds 38 candidate
    # legs across 34 boards on production, so the widened `IN` list is noise
    # against the 429 the sibling already sends.
    return [
        o
        for o in market.outcomes
        if needs_trade_evidence(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            in_exclusive_field=in_exclusive_field,
        )
        or needs_unbacked_ask_evidence(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_probability", None)),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            in_exclusive_field=in_exclusive_field,
            volume_24h=getattr(o, "volume_24h", None),
            volume_24h_at=getattr(o, "volume_24h_at", None),
            last_seen_at=getattr(o, "last_updated", None),
        )
    ]


def _newest_capture_per_outcome(outcome_ids: list[int], bookmaker: str):
    """`(outcome_id, captured_at)`: each leg's newest capture on `bookmaker` (#2316).

    The two trade reads below join their rows back to this. It used to be
    `max(captured_at) ... GROUP BY outcome_id` over `futures_odds_snapshots`,
    and Postgres has no index skip scan, so that form read EVERY snapshot a
    leg has ever had to find its newest one — a cost that grows for as long as
    we keep pricing the market, on an append-only 51 GB table. Production
    `pg_stat_statements`, 2026-10-10: ~2.8 s mean, 10-21 s max, ~285k buffers
    per call to return ~1,150 rows. One `EXPLAIN ANALYZE` over 150 hockey
    season legs: 57,430 index entries and 1,587 ms.

    Here each leg asks the question by itself, as an UNGROUPED `max()` keyed on
    its own id, which Postgres answers as a one-row backward probe of
    `(outcome_id, bookmaker, captured_at DESC)`. Same 150 legs: 9 ms. `max()`
    is kept on purpose rather than `ORDER BY ... LIMIT 1`, because `captured_at`
    is nullable and `max()` already ignores NULLs exactly as the old aggregate
    did; a leg with no capture gets NULL here and joins nothing, as before.

    Driven from `futures_outcomes` by primary key so it stays portable SQL (the
    SQLite rigs run these readers too). That is the same set of legs: the FK
    `futures_odds_snapshots_outcome_id_fkey` is validated, so no snapshot names
    an outcome that is not there. Proven on production as a FULL OUTER JOIN of
    old and new answers: 0 mismatches over 376 Kalshi legs (max price), 400
    Polymarket legs (raw rows, 148 with a NULL price) and 376 Kalshi legs (raw).

    The inner snapshot table is an alias so the correlation can only bind to
    the outcome row, never to the outer query's own `futures_odds_snapshots`.
    """
    capture = aliased(FuturesOddsSnapshot)
    newest_at = (
        select(func.max(capture.captured_at))
        .where(
            capture.outcome_id == FuturesOutcome.id,
            capture.bookmaker == bookmaker,
        )
        .correlate(FuturesOutcome)
        .scalar_subquery()
    )
    return (
        select(
            FuturesOutcome.id.label("outcome_id"),
            newest_at.label("captured_at"),
        )
        .where(FuturesOutcome.id.in_(outcome_ids))
        .subquery()
    )


async def _newest_kalshi_trades(db: AsyncSession, outcome_ids: list[int]) -> dict:
    """`{outcome_id: last_price}` at each leg's newest Kalshi capture (#7632).

    THE ONLY PART OF THIS ARM THAT TOUCHES THE DATABASE, AND IT IS KEYED ON AN
    ID LIST RATHER THAN A MARKET SO IT BATCHES. The page passes one board's
    candidates; the snapshot builder passes every candidate leg on the feed's
    whole pool and gets back one dict in ONE query. The per-board loop the naive
    wiring would have written is what turns "share the page's rule" into a
    per-card query on `/api/feed`, which decision (b) explicitly forbids.

    An empty id list is answered WITHOUT a query — a pool whose boards hold no
    candidate must cost nothing, which is the same property the per-market arm
    had before the split.
    """
    if not outcome_ids:
        return {}
    newest = _newest_capture_per_outcome(outcome_ids, KALSHI_BOOKMAKER)
    rows = await db.execute(
        select(
            FuturesOddsSnapshot.outcome_id,
            func.max(FuturesOddsSnapshot.last_price),
        )
        .join(
            newest,
            and_(
                FuturesOddsSnapshot.outcome_id == newest.c.outcome_id,
                FuturesOddsSnapshot.captured_at == newest.c.captured_at,
            ),
        )
        .where(FuturesOddsSnapshot.bookmaker == KALSHI_BOOKMAKER)
        .group_by(FuturesOddsSnapshot.outcome_id)
    )
    # Two Kalshi snapshots can share one `captured_at`; the aggregate above keeps
    # the HIGHEST last_price among them, which is the fail-open direction — any
    # trade evidence at all leaves the price on the page.
    return {outcome_id: price for outcome_id, price in rows.all()}


_KALSHI_MULTI_SELECTION_AWARD_SERIES = frozenset({
    "KXNBAROOKIE1STTEAM",
    "KXNBAROOKIE2NDTEAM",
    "KXNBAAWARDFIN",
})


def _unsupported_price_verdicts(
    market: FuturesMarket, candidates: list, latest_trade: dict
) -> set[int]:
    """Which candidates the two #5611/#7747 screens actually refuse (#7632 split).

    Pure, so the batched builder and the per-market page path reach an identical
    answer from an identical dict. `latest_trade` may hold ids belonging to other
    boards when the builder batches — every read here is keyed on `o.id`, so a
    wider dict is inert rather than contaminating.
    """
    in_exclusive_field = market_is_proved_exclusive_field(
        getattr(market, "market_type", None),
        getattr(market, "market_metadata", None),
    )
    series = (getattr(market, "external_id", None) or "").partition("-")[0]
    multi_selection_award = series in _KALSHI_MULTI_SELECTION_AWARD_SERIES
    return {
        o.id
        for o in candidates
        if price_is_unsupported(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            _as_float(latest_trade.get(o.id)),
            has_trade_evidence=o.id in latest_trade
            and latest_trade[o.id] is not None,
            in_exclusive_field=in_exclusive_field,
        )
        # #7747. An OR, so the arms are independent screens over one candidate
        # list: a leg ANY arm refuses is withheld, and none can acquit what
        # another caught. #8210 added a third below and relies on that property —
        # it deliberately OVERLAPS the arm above on legs printing at their ask.
        or price_is_an_unbacked_ask(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_probability", None)),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            _as_float(latest_trade.get(o.id)),
            has_trade_evidence=o.id in latest_trade
            and latest_trade[o.id] is not None,
            in_exclusive_field=in_exclusive_field,
            # `getattr` throughout: a caller may hand this a market whose
            # outcomes never loaded these columns, and an absent stamp must read
            # as "do not withhold" rather than raise.
            volume_24h=getattr(o, "volume_24h", None),
            volume_24h_at=getattr(o, "volume_24h_at", None),
            last_seen_at=getattr(o, "last_updated", None),
        )
        # #8210. The third independent screen over the same candidate list, and
        # the one that reaches rule 2's trade-evidence exemption: the arm above
        # needs the price AT its own ask, so a stale trade locating a price
        # strictly INSIDE an unbid spread is acquitted by every other arm. Same
        # book shape and same volume term as its sibling; only the position of
        # the print in the spread differs.
        or price_is_an_unbacked_majority(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_probability", None)),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            _as_float(latest_trade.get(o.id)),
            # A stored snapshot with a null trade can inform the award
            # guard. A missing snapshot still provides no evidence.
            has_trade_evidence=o.id in latest_trade,
            in_exclusive_field=in_exclusive_field,
            multi_selection_award=multi_selection_award,
            volume_24h=getattr(o, "volume_24h", None),
            volume_24h_at=getattr(o, "volume_24h_at", None),
            last_seen_at=getattr(o, "last_updated", None),
        )
    }


def _refuted_midpoint_candidates(market: FuturesMarket) -> list:
    """The legs of this market worth a venue trade read (#7632 split).

    Carries the VENUE GATE, not just the per-leg screen, so a caller batching
    many boards cannot accidentally send a non-midpoint venue's legs to the
    trade query: a market whose source is outside `MIDPOINT_TRADE_SOURCES` has
    no candidates at all, exactly as the per-market arm decided before the
    split. See `_unsupported_price_candidates` for why the screen is a named
    function rather than an inline comprehension.
    """
    if (market.source or "").strip().lower() not in MIDPOINT_TRADE_SOURCES:
        return []
    return [
        o
        for o in market.outcomes
        if needs_trade_disconfirmation(
            market.source,
            o.resolution_source,
            _as_float(o.current_probability),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
        )
    ]


async def _newest_venue_trade_rows(
    db: AsyncSession, venue: str, outcome_ids: list[int]
) -> list:
    """Raw `(outcome_id, last_price)` at each leg's newest capture on `venue`.

    RAW ROWS, NOT A DICT, because this arm's pick is not "the max" — it is "the
    trade closest to the served midpoint among those sharing the newest
    `captured_at`", and that choice needs the served probability, which is a
    per-market fact. So the query batches (one call per venue for the whole
    pool) and `_closest_trade_by_outcome` folds per board. Empty id list costs
    no query, same as the Kalshi sibling.
    """
    if not outcome_ids:
        return []
    newest = _newest_capture_per_outcome(outcome_ids, venue)
    rows = await db.execute(
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.last_price,
        )
        .join(
            newest,
            and_(
                FuturesOddsSnapshot.outcome_id == newest.c.outcome_id,
                FuturesOddsSnapshot.captured_at == newest.c.captured_at,
            ),
        )
        .where(FuturesOddsSnapshot.bookmaker == venue)
    )
    return list(rows.all())


def _closest_trade_by_outcome(candidates: list, rows: list) -> dict:
    """Per leg, the newest-capture trade nearest its served midpoint (#7632 split).

    ⚠️ ROWS BELONGING TO OTHER BOARDS ARE SKIPPED, NOT FOLDED. When the snapshot
    builder batches a venue's whole pool into one query, this fold is handed
    rows for legs that are not this market's candidates. Keying the skip on
    `served` membership keeps the batched answer byte-identical to the
    per-market one — and on the per-market path every row is a candidate, so
    the filter is a no-op there rather than a behaviour change.
    """
    served = {o.id: _as_float(o.current_probability) for o in candidates}
    latest_trade: dict[int, float] = {}
    for outcome_id, last_price in rows:
        if outcome_id not in served:
            continue
        price = _as_float(last_price)
        if price is None:
            continue
        target = served.get(outcome_id)
        held = latest_trade.get(outcome_id)
        if held is None or (
            target is not None and abs(price - target) < abs(held - target)
        ):
            latest_trade[outcome_id] = price
    return latest_trade


def _refuted_midpoint_verdicts(
    market: FuturesMarket, candidates: list, latest_trade: dict
) -> set[int]:
    """Which candidates the #5876 midpoint screen actually refuses (#7632 split)."""
    return {
        o.id
        for o in candidates
        if midpoint_refuted_by_last_trade(
            market.source,
            o.resolution_source,
            _as_float(o.current_probability),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            latest_trade.get(o.id),
            has_trade_evidence=o.id in latest_trade,
        )
    }


def _book_refuted_outcome_ids(market: FuturesMarket) -> set[int]:
    """Which of this market's outcomes serve a price their own book prices out.

    #6532, the third arm, and the only one of the three that costs NOTHING. Its
    two siblings each need the newest snapshot to answer "did this ever trade" or
    "what did it last trade at", so each runs a query. This one reads the served
    price against the book columns sitting on the same row — three fields of one
    write — so it is a pass over outcomes already in memory, no query, no index,
    and synchronous for that reason rather than by omission.

    The rule and everything measured about it are in
    :func:`app.utils.futures_unsupported_price.price_refuted_by_live_book`,
    including why a graded winner is never touched and why a graded loser is asked
    only half the predicate.
    """
    return {
        o.id
        for o in market.outcomes
        if price_refuted_by_live_book(
            market.source,
            o.resolution_source,
            o.is_winner,
            _as_float(o.current_probability),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
        )
    }


def _empty_book_outcome_ids(market: FuturesMarket) -> set[int]:
    """Which of this market's outcomes price a book with nothing in it (#6757).

    WHAT A READER SAW. ``/futures/57777176`` — "NBA: Steph Curry Next Team" —
    printed a confident percentage against all 30 teams and not one of them was
    a traded price: sixteen clubs read **48%**, the ladder summed to **1112.5%**,
    and every row had been written in one batch six weeks earlier
    (``2026-08-01 00:19:45.171081``, identical microsecond ⇒ one batch writer).
    The same shape answers a real election on ``/futures/110297`` — "Who will win
    the 2026 Colombia Senate election? Opposition 49.7% / Government Alliance
    49.1%" — and prices five mutually exclusive CPI rungs at 50% EACH on
    ``/futures/109681``.

    THE RULE IS NOT NEW AND IS NOT RE-DERIVED HERE. This is
    :func:`_leg_prices_an_empty_book`, the same object the grouped feed already
    calls at its one shipped call site, which is in turn #5247's measured
    predicate wearing #6727's spread form. The defect was never the rule; it was
    that this route never asked it. Three read surfaces refuse these rows today
    — ``game-markets``, the search slice and the grouped feed — so the strip and
    the page a reader opens FROM the strip disagreed about the same row in the
    same hour, which is the whole of #6757.

    WITHHELD, NOT SKIPPED, and that is the difference from the grouped-feed call
    site rather than an inconsistency with it. The strip drops the leg from a
    five-row card; this page IS the full field, and dropping sixteen clubs out of
    "Steph Curry Next Team" would answer a question nobody asked. The price is
    nulled and the row stays — the contract the three arms above already keep.

    A GRADED ROW IS EXEMPT, and that exemption is this function's and NOT the
    shared predicate's. ``_leg_prices_an_empty_book`` reads three price columns
    and knows nothing about settlement, which is right for the strip; here it
    would mean withholding the price of a row the venue has already decided, and
    #6532 states the cost of that plainly — withholding a settled row deletes a
    result. Settled means settled, so the grade is checked HERE, at the call
    site, rather than by teaching the shared rule a fourth condition its three
    other consumers never asked for. Measured on production 2026-09-17: 58 of the
    4,192 legs this arm reaches are graded, so the exemption costs the ship
    nothing and buys back the one class where withholding does harm.

    NO QUERY, like :func:`_book_refuted_outcome_ids` directly above and for the
    same reason — the columns it reads are on rows already in memory.

    MEASURED BEFORE SHIPPING (production, 2026-09-17): 4,192 legs across 2,402
    open markets. 1,973 of those markets are left with no priced leg at all, and
    1,910 of THOSE carry one or two legs — an untraded binary whose only book is
    empty, which is exactly the row that should print nothing rather than a
    manufactured coin flip. Eleven markets with six or more legs blank entirely.

    A RETRACTION IS NOT A GRADE, and this is the one refinement the exemption
    has needed since it shipped. ``ungradeable_result`` is the no-result
    sentinel (CAL-P056): a leg carrying it has been declared unknowable, not
    decided, so there is no result for the exemption to protect — only the
    empty-book midpoint it was written to withhold. ``/futures/2951399`` printed
    thirteen identical 49s under that badge on an open market resolving in
    2027, ``prices_withheld: 0`` beneath them.

    THE TEST IS NOT WRITTEN HERE. :func:`row_carries_a_verdict` (#6876) is the
    codebase's one spelling of "is there a grade at all", and this route's price
    rails already ask it — ``needs_trade_evidence`` and
    ``price_refuted_by_live_book`` both call it. This arm and the chart arm in
    :func:`_drop_unsupported_snapshot_points` call the same function so the
    ladder, the graph and the rails cannot read one row three ways. Every other
    non-null source keeps the exemption exactly as before: whether a terminal
    no-winner source such as ``all_losers`` should also yield is a settlement
    question, and the tests pin today's answer so it is changed visibly.
    """
    return {
        o.id
        for o in market.outcomes
        if not row_carries_a_verdict(getattr(o, "resolution_source", None))
        and _leg_prices_an_empty_book(o)
    }


def _unlocated_in_broken_field_outcome_ids(
    market: FuturesMarket, already_withheld: set[int]
) -> set[int]:
    """Which outcomes price a book that bounds nothing, inside a field that cannot be one (#7059).

    The fifth arm, and the second one to cost no query: like
    :func:`_book_refuted_outcome_ids` it reads columns already on rows in memory.

    The rule, the specimen and every number behind it are in
    :func:`app.utils.futures_unsupported_price.price_is_unlocated_in_broken_field`
    and its field-level half :func:`field_names_two_favourites` — including why the
    recency question is never asked and why both halves are load-bearing.

    ``already_withheld`` IS THE WHOLE REASON THIS ARM TAKES AN ARGUMENT AND THE
    OTHERS DO NOT. Its gate is a fact about the COLUMN A READER SEES, so it has to
    be computed over the legs that survive the four arms above rather than over
    every stored row — "the caller passes the list it will actually print, because
    that is the set whose coherence the page is claiming"
    (``classify_field_openings``). On the specimen this is not academic: Tyson Fury
    stores 0.97 and is ALREADY refused by :func:`_book_refuted_outcome_ids` (he
    serves above his own ask), so counting stored rows would credit the field with a
    favourite no reader is shown. It still names two — Usyk 0.93 and Kabayel 0.87 —
    so the gate holds either way here, but a rule about what a page claims may not
    be measured on rows the page withholds.

    THE ORDER IS THEREFORE FIXED AND ONE-PASS. This arm runs last, over the survivors
    of the other four, and its own refusals do NOT re-open the gate. Iterating to a
    coherent column would be chasing a sum, which this module does not do
    (gotcha #21, withholding never rewriting); one pass also makes the result
    independent of the order ids happen to arrive in.

    A MARKET WHOSE SHAPE IS NOT PROVED EXCLUSIVE NEVER REACHES THE GATE, and the
    check fails closed on absent metadata exactly as it does at the #6846 call site
    above — ``market_is_proved_exclusive_field`` reads the persisted classifier, not
    ``futures_markets.mutually_exclusive``, which defaults to true and is evidence of
    nothing.
    """
    if not market_is_proved_exclusive_field(
        getattr(market, "market_type", None),
        getattr(market, "market_metadata", None),
    ):
        return set()
    served = [o for o in market.outcomes if o.id not in already_withheld]
    if not field_names_two_favourites(
        [_as_float(getattr(o, "current_probability", None)) for o in served]
    ):
        return set()
    return {
        o.id
        for o in served
        if _as_float(getattr(o, "current_probability", None)) is not None
        and price_is_unlocated_in_broken_field(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
        )
    }


def _unsupported_head_outcome_ids(
    market: FuturesMarket, already_withheld: set[int]
) -> set[int]:
    """Which outcomes would head a proved field on a print nobody bids on or trades (#8265).

    The sixth arm, and like #7059's it costs no query and takes the ids the arms
    above refused, for the same reason: its ceiling is a fact about the column a
    reader is SHOWN. On the specimen that is the whole case — Jakub Mensik's 3¢ bid
    is the only bid on the board, and #7747 already withholds his price, so counting
    stored rows would credit the field with support no reader sees.

    Runs after #7059's arm and reads its refusals too. The rule and its measurement
    live on :func:`unsupported_legs_above_the_supported_head`.

    A board carrying a verdict is a RESULT and is skipped whole (settled means
    settled), and a market whose shape is not proved exclusive never reaches the
    rule — outside a one-winner field there is no column for a leg to head.
    """
    if not market_is_proved_exclusive_field(
        getattr(market, "market_type", None),
        getattr(market, "market_metadata", None),
    ):
        return set()
    outcomes = getattr(market, "outcomes", None) or []
    if _board_has_a_verdict(outcomes):
        return set()
    served = []
    for o in outcomes:
        if o.id in already_withheld:
            continue
        probability = _as_float(getattr(o, "current_probability", None))
        if probability is None:
            continue
        served.append(
            (
                o.id,
                probability,
                leg_has_no_live_support(
                    market.source,
                    getattr(o, "resolution_source", None),
                    _as_float(getattr(o, "current_yes_bid", None)),
                    _as_float(getattr(o, "current_yes_ask", None)),
                    volume_24h=getattr(o, "volume_24h", None),
                    volume_24h_at=getattr(o, "volume_24h_at", None),
                    last_seen_at=getattr(o, "last_updated", None),
                ),
            )
        )
    return unsupported_legs_above_the_supported_head(served)


def _board_has_a_verdict(outcomes) -> bool:
    """Has anybody actually settled this board? (#8011 / CERT-3298)

    🔴 `status == 'open'` DOES NOT ANSWER THIS, which is the whole reason this
    exists. Gotcha #33: settled Kalshi markets stay `status='open'` in our
    database because polling only ever sees open markets. 444 of the 969 boards
    #8011's predicate admits carry a verdict under this test, and every one of
    them is a RESULT that must survive — `/futures/413`'s "Jalen Brunson 99%" is
    the Finals MVP answer, with `api_settlement` on all 57 legs.

    Delegates to `futures_liveness.leg_is_graded`, the shared semantics #7387
    and #4788 already read, rather than testing `is_winner` here. That column is
    `default=False`, so False is what a row is BORN with and not a grader's
    decision, and `ungradeable_result` is a RETRACTION of a fabricated loss
    rather than a verdict. A local test would get both wrong.
    """
    from app.utils.futures_liveness import leg_is_graded

    return any(
        leg_is_graded(
            getattr(o, "is_winner", None), getattr(o, "resolution_source", None)
        )
        for o in outcomes
    )


async def _fleet_newest_observation(
    db: AsyncSession, market: FuturesMarket, *other_markets: FuturesMarket
) -> "datetime | None":
    """The newest futures leg observation the system holds, anywhere (#8011).

    `unobserved_board_keys` needs a reference a single board cannot supply: is
    anyone writing prices AT ALL right now? This is that reference, and it is
    deliberately the same column the per-leg rule reads
    (`futures_outcomes.last_updated`) so the two lags are commensurable.

    🔴 SKIPPED ENTIRELY FOR ANY BOARD THAT COULD NOT QUALIFY, and that gate is
    the reason this route's query count does not move. Every stamp is in the
    past, so `fleet <= now`; a board whose own newest stamp is inside the floor
    of `now` therefore cannot be inside it of the fleet either, and the read
    would only confirm what `board_cannot_be_unobserved` already proved. That
    covers ~92% of boards (2,662 of 31,716 open priced boards carry a leg stamp
    past the floor) and, in particular, every board LAT-P127's cache guard
    exercises — its fixtures carry no leg stamp at all.

    SINCE #2077 THE STATUS GATE ADMITS "resolved" TOO, and the cost of that is
    bounded by the two refusals immediately below it rather than by the status
    test. A graded board still costs no query (the verdict early-return), and a
    board whose own newest stamp is recent still costs no query
    (`board_cannot_be_unobserved`, which is status-agnostic and unchanged). What
    is newly eligible is exactly the defect population: settled, ungraded, and
    last observed beyond the floor. This route serves ONE board per request, so
    the worst case it adds is a single 0.042 ms Index Only Scan Backward to a
    detail page that would otherwise print a coin flip. A multi-board caller
    can share that same fleet observation when any of its boards qualify.

    The bound is one-directional by construction: it can only suppress the
    read, never cause a withhold. `unobserved_board_keys` still decides against
    the fleet, so a fleet-wide stall still withholds nothing.

    NOT MEMOISED, ON PURPOSE. `ix_futures_outcomes_last_updated` makes this an
    Index Only Scan Backward: measured on production 2026-09-22 at **0.042 ms**
    / 6 shared hit blocks against a 1.1M-row parent table. A cache would buy
    nothing measurable on top of the gate above, and would cost the two things
    caches cost here — a per-uvicorn-worker copy (`WEB_CONCURRENCY=2`, so the
    hit rate is not what a single process reports) and a stale reference that
    could only ever push a live board towards being read as unobserved.

    Returns None — which `unobserved_board_keys` reads as "withhold nothing" —
    if the board cannot qualify, if the query fails, or if the table is empty. A
    database this route could not reach must degrade to today's behaviour, never
    to a blanked board.
    """
    from app.utils.market_staleness import (
        board_cannot_be_unobserved,
        board_touched_at,
    )

    # 🔴 #2077, CERT-3308 — THIS LINE IS WHY WIDENING THE FORMATTER ALONE
    # CHANGED NOTHING A READER COULD SEE.
    #
    # `_format_market_detail` names both statuses so an ungraded settled board
    # reaches `unobserved_board_keys`. But the rule fails open on a missing
    # `fleet_newest_observation`, and THIS function — the only thing that
    # supplies it — returned None without a query for every status but "open".
    # So the widened formatter was handed None on exactly the population it had
    # just been widened for, took its fail-open path, and withheld nothing:
    # `/futures/56916563` went on serving `Under 0.5`, and an exact-sha
    # reproduction read `resolved_result=None db_execute_awaits=0`.
    #
    # THE GENERAL LESSON, AND IT IS THE SECOND TIME THIS RULE HAS BITTEN THIS
    # SHIP: the same `status == "open"` test lived in three places, not two.
    # Mutation caught the dead copy INSIDE the formatter; it could not see this
    # one, because the tests inject `fleet_newest_observation` directly into
    # `_format_market_detail` and therefore never traverse this seam. A guard
    # that hands the callee an input the caller never supplies cannot observe a
    # caller that never supplies it — which is why the repair below is a
    # ROUTE-level regression, not another formatter unit.
    #
    now = datetime.now(timezone.utc)
    for candidate in (market, *other_markets):
        if getattr(candidate, "status", None) not in ("open", "resolved"):
            continue
        outcomes = getattr(candidate, "outcomes", None) or []
        if _board_has_a_verdict(outcomes):
            continue
        if not board_cannot_be_unobserved(
            ((o.id, o.last_updated) for o in outcomes),
            board_touched_at=board_touched_at(candidate),
            now=now,
        ):
            break
    else:
        return None

    try:
        return (
            await db.execute(select(func.max(FuturesOutcome.last_updated)))
        ).scalar_one_or_none()
    except Exception:
        logger.warning("fleet newest observation unavailable", exc_info=True)
        return None


async def withheld_price_outcome_ids_for_markets(
    db: AsyncSession, markets: Sequence[FuturesMarket]
) -> dict[int, set[int]]:
    """`_withheld_price_outcome_ids` over MANY boards, in a constant query count.

    #7632. THE CARD AND THE PAGE DISAGREED BECAUSE ONLY THE PAGE ASKED. The
    detail route refuses a leg's price through the five arms above; the Discover
    card ran none of them, so it printed prices the page withholds and divided by
    a mass that still contained them. Three boards on the served feed of
    2026-09-23 06:09Z, matched by outcome id:

        61960017  WTA Seoul      card: Birrell/Tararudee/Bondar all 49%
                                 page: prices 1 of 16 legs, all three withheld
        61437318  WTA Singapore  card leader Kasatkina 31%
                                 page withholds her; hero is Eala 28.5%
        61734333  LPGA NW Ark.   page withholds 100 of 144, prints Yamashita 11%
                                 card divides by the fuller mass, prints 7.65%

    Seoul is the one to read: a card offering three co-favourites at 49% lands on
    a page that will not price any of them. Singapore is worse in kind — the card
    NAMES A LEADER the page refuses, so a tap inverts the story.

    ═══ WHY A SEPARATE ENTRY POINT AND NOT A LOOP ═══

    Calling the per-market helper once per board is the obvious wiring and it is
    the one thing decision (b) forbids: two queries per card on the feed's build
    path. Both database arms are `IN`-list reads keyed on a bookmaker, so they
    batch — the Kalshi arm collapses to ONE query for the entire pool, and the
    midpoint arm to one per distinct venue, of which `MIDPOINT_TRADE_SOURCES`
    admits two. **Four queries at most, whatever the pool size.** That is
    strictly cheaper than the per-board budget the decision approved.

    The arms are not re-implemented here. Each was split into (candidates → trade
    read → verdict) and this function reuses the same pure halves the page path
    calls, which is `_withheld_price_outcome_ids`'s own "ONE HELPER, NOT A FIFTH
    SPELLING" obeyed rather than evaded: a sixth arm, or a change to any existing
    one, reaches the card and the page together or not at all.

    ⚠️ THE CALLER MUST HAVE LOADED `resolution_source`, `volume_24h`,
    `volume_24h_at` AND `is_winner`. Every read of them below is a `getattr`
    defaulting to `None`, which on a `load_only`-restricted row is not a crash —
    it is a screen that quietly refuses nothing, the "a DIFFERENT feed, not a
    cheaper one" failure `futures_market_snapshot` exists to prevent. Those four
    are in `OUTCOME_LOAD_ONLY_EXTRA` for exactly this reason, and
    `test_card_and_page_share_the_withheld_set_7632` pins them there.

    Returns a mapping keyed by market id, holding an empty set for a board that
    refuses nothing. A board is OMITTED only when evaluating it raised — see the
    per-market guard below. Missing and empty are different facts downstream
    (see `_drop_withheld_price_legs`), which is what makes omission safe.

    ⚠️ ONE BAD BOARD MUST NEVER WIPE THE POOL (gotcha #42). This runs OUTSIDE
    the serializers' per-item `try`, in the shared-artifact builder, so an
    unconverted string on one market's leg would otherwise take down the whole
    futures pass — `test_poison_market_does_not_wipe_futures_pass` caught
    exactly that on the first cut of this function and was right to. Every
    market is therefore evaluated under its own guard, and a board that raises
    is left OUT of the map, which the consumer reads as "not computed" and so
    serves at its pre-#7632 numbers. The failure direction is one card keeping
    the prices the page refuses, never a feed with no futures in it.
    """
    unsupported_candidates: dict[int, list] = {}
    midpoint_candidates: dict[int, list] = {}
    kalshi_ids: list[int] = []
    venue_ids: dict[str, list[int]] = {}
    unreadable: set[int] = set()

    for market in markets:
        try:
            unsupported = _unsupported_price_candidates(market)
            midpoint = _refuted_midpoint_candidates(market)
        except Exception:
            logger.warning(
                "withheld-price screen could not read market %s — its card "
                "keeps its pre-#7632 prices",
                getattr(market, "id", None),
                exc_info=True,
            )
            unreadable.add(getattr(market, "id", None))
            continue
        if unsupported:
            unsupported_candidates[market.id] = unsupported
            kalshi_ids.extend(o.id for o in unsupported)
        if midpoint:
            midpoint_candidates[market.id] = midpoint
            venue = (market.source or "").strip().lower()
            venue_ids.setdefault(venue, []).extend(o.id for o in midpoint)

    kalshi_id_set = set(kalshi_ids)
    kalshi_midpoint_ids = venue_ids.get(KALSHI_BOOKMAKER)
    venue_rows: dict[str, list] = {}
    if kalshi_id_set and kalshi_midpoint_ids:
        # #11931: both arms read `(outcome_id, last_price)` at each leg's newest
        # Kalshi capture from the 51 GB `futures_odds_snapshots` table. Query
        # the union ONCE and fold `max(last_price)` in Python identically to
        # `_newest_kalshi_trades` while reusing the raw rows for the midpoint
        # arm (`_closest_trade_by_outcome` filters by each board's candidates).
        kalshi_union = sorted(kalshi_id_set | set(kalshi_midpoint_ids))
        kalshi_rows = await _newest_venue_trade_rows(
            db, KALSHI_BOOKMAKER, kalshi_union
        )
        venue_rows[KALSHI_BOOKMAKER] = kalshi_rows
        latest_kalshi_trade: dict = {}
        for oid, price in kalshi_rows:
            if oid not in kalshi_id_set:
                continue
            if oid not in latest_kalshi_trade:
                latest_kalshi_trade[oid] = price
            elif price is not None and (
                latest_kalshi_trade[oid] is None or price > latest_kalshi_trade[oid]
            ):
                latest_kalshi_trade[oid] = price
    else:
        latest_kalshi_trade = (
            await _newest_kalshi_trades(db, sorted(kalshi_id_set))
            if kalshi_id_set
            else {}
        )

    for venue, ids in venue_ids.items():
        if venue in venue_rows:
            continue
        venue_rows[venue] = await _newest_venue_trade_rows(
            db, venue, sorted(set(ids))
        )

    withheld: dict[int, set[int]] = {}
    for market in markets:
        if getattr(market, "id", None) in unreadable:
            continue
        try:
            ids: set[int] = set()
            unsupported = unsupported_candidates.get(market.id)
            if unsupported:
                ids |= _unsupported_price_verdicts(
                    market, unsupported, latest_kalshi_trade
                )
            midpoint = midpoint_candidates.get(market.id)
            if midpoint:
                venue = (market.source or "").strip().lower()
                ids |= _refuted_midpoint_verdicts(
                    market,
                    midpoint,
                    _closest_trade_by_outcome(midpoint, venue_rows.get(venue, [])),
                )
            ids |= _book_refuted_outcome_ids(market)
            ids |= _empty_book_outcome_ids(market)
            # Last, and reading the four above — the same composition order as
            # the per-market helper, because this arm's gate is a fact about
            # what the OTHER four already took away.
            ids |= _unlocated_in_broken_field_outcome_ids(market, ids)
            ids |= _unsupported_head_outcome_ids(market, ids)
        except Exception:
            logger.warning(
                "withheld-price screen could not grade market %s — its card "
                "keeps its pre-#7632 prices",
                getattr(market, "id", None),
                exc_info=True,
            )
            continue
        withheld[market.id] = ids
    return withheld
