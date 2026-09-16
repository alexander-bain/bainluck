"""A lone ask on an empty Kalshi book is not a price — the shared predicate.

WHY THIS FILE EXISTS. ``_kalshi_yes_probability`` (``app/tasks/kalshi.py``)
learned this on 2026-07-13 in ``52eee9b6`` (Queue #182): an ask-only book is
trusted only up to :data:`ASK_ONLY_TRUSTED_MAX`, and above it the poller stores
nothing rather than publish the ask. The guard works — since that commit there
is not one stored Kalshi opening whose book was a lone ask above 0.50.

But it guards the WRITE, and nothing guarded the PROMOTION. ``backfill_winners``
Phase 0c-repair copies a resolved outcome's earliest snapshot into
``opening_probability`` keyed only on ``opening_probability IS NULL``, without
looking at the book that snapshot recorded. So every row the poller wrote before
the guard existed is still promoted into the published calibration curve, and
nulling one restores it within a 6-hour cycle — the regression the phase's own
comment predicted ("One-time cleanup that became an ongoing regression source").

WHAT IT COSTS, measured on production (#4745), resolved Kalshi legs whose
earliest snapshot is a lone ask on an empty book, captured before the guard:

    sport         legs    mean published   actually won
    baseball     12,451       0.949           14.5%
    hockey        8,993       0.886            7.8%
    golf          3,055       0.951            7.0%
    football      1,167       0.987            5.7%
    geopolitics     156       0.990            0.6%
    ---------------------------------------------------
    every family 34,281       ~0.94           ~14%

Nobody would pay a cent for YES; somebody left an ask at 98c; we published 98%.

THE ASYMMETRY IS THE POINT, and it is measurable in both directions. Earliest
snapshot per leg, 1-in-211 sample of all resolved Kalshi legs:

    book shape at capture          legs   mean stored   actually won
    lone ASK, zero bid, no trade    659      0.369          6.2%
    lone BID, ask at 1.00           189      0.949         93.7%
    tight book                      872      0.341         33.3%

A lone **bid** is a real price — somebody will pay that — and it grades almost
perfectly. A lone **ask** on a book nobody bids into is an offer no one took,
and it grades as a near-total loss. Only the ask side is refused here.

This module holds the rule once, in both dialects, because the promotion is SQL
and the poller is Python and a price policy that exists twice drifts (the same
reasoning that put ``kalshi_candle_price`` beside
``event_chart_backfill.normalize_candle``). Collapsing all three onto one policy
object is the standing follow-up ``4745-ONE-KALSHI-CANDLE-PRICE-POLICY``.

:func:`book_refutes_price` moved in here from ``app.tasks.kalshi`` for that same
reason (#6532): it was written as the poller's private ``_book_refutes_trade``,
and the serve layer needs the identical question asked of a stored price. A
price policy that exists twice drifts, so it is held once and imported by both.
"""

from __future__ import annotations

from typing import Optional

#: Highest ask an ask-only book may carry and still be trusted as a price.
#: Bound to ``app.tasks.kalshi._kalshi_yes_probability`` rule 3 by
#: ``tests/test_kalshi_empty_book.py``; changing one without the other is the
#: drift this constant exists to make loud.
ASK_ONLY_TRUSTED_MAX = 0.50

#: ``futures_odds_snapshots.bookmaker`` for the venue this rule is about. The
#: SQL form carries it because its only caller (Phase 0c-repair) reads EVERY
#: source's snapshots, and this policy is Kalshi's alone — see
#: :func:`lone_ask_on_empty_book_sql`.
KALSHI_BOOKMAKER = "kalshi"


def is_lone_ask_on_empty_book(
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    last_price: Optional[float],
) -> bool:
    """True when this book carries no price, only an untaken offer.

    All three arguments are decimal probabilities (0-1), matching what
    ``futures_odds_snapshots`` stores and what ``kalshi_api`` parses.

    A missing bid is NOT the same as a zero bid: ``None`` means the poller never
    recorded a book at all (the candle rails store no bid/ask), and this
    predicate must not claim to know anything about those rows. Only an
    explicitly zero bid — nobody paying anything — is evidence.
    """
    if yes_bid is None or yes_ask is None:
        return False
    if yes_bid > 0:
        return False
    if last_price is not None and last_price > 0:
        return False
    return yes_ask > ASK_ONLY_TRUSTED_MAX


#: Tolerance for :func:`book_refutes_price`, in decimal probability. Kalshi
#: quotes on a one-cent grid (the venue's own ``price_level_structure`` reads
#: ``linear_cent``), so half a cent sits below the smallest move the venue can
#: make and cannot mask a real one.
BOOK_REFUTES_PRICE_EPSILON = 0.005


def book_refutes_price(
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    price: float,
) -> bool:
    """True when the LIVE book prices out this number, whatever produced it.

    WRITTEN FOR THE WRITER AND NOW READ BY BOTH SIDES (#5121, then #6532). Rule 2
    of ``app.tasks.kalshi._kalshi_yes_probability`` prefers a real trade to a wide
    book, and that is right when the book is uninformative. It is wrong when the
    book has MOVED past the trade: an ask of 0.09 means anyone may buy at nine
    cents right now, so a trade at 0.52 is not evidence of anything except that
    somebody once paid more. The trade is a memory; the quote is an offer.

    MEASURED (#5121, production 2026-09-11 ~17:00Z). Every violating rung of the
    two ladder series in that issue — 12 of 12, checked against Kalshi's own
    ``/trade-api/v2/markets/{ticker}`` — stored EXACTLY the venue's ``last_price``
    while that price sat above the venue's own ``yes_ask``:

        KXNBAWINS-27MIA-60   ours 0.5200   venue last 0.5200   venue ask 0.0900
        KXNFLWINS-27CLE-13   ours 0.1000   venue last 0.1000   venue ask 0.0500
        KXNFLWINS-27SF-16    ours 0.1700   venue last 0.1700   venue ask 0.0800
        ... 9 more, same shape, zero mismatches

    That is what a reader saw as Miami's "60+ wins 52%" printed ABOVE its own
    "55+ wins 14.5%" — a cumulative ladder going up, which no season can make
    true. The rung is not a disagreement between us and the venue; it is us
    choosing the venue's stalest number over its freshest one.

    🔴 THE ARGUMENT IS A NUMBER, NOT A PROVENANCE, AND THAT IS WHY IT PORTS TO THE
    READ SIDE (#6532). This asks whether the quote prices a number out; it never
    asks where the number came from, so the answer is the same for a trade the
    writer is about to store and for a price the serializer is about to publish.
    It reads three columns of ONE row — the two book columns and the number — so
    it is the module's usual shape: one write of ours against another field of the
    same write, never our stored value against a fresh venue read.

    🔴 THE EMPTY BOOK IS DELIBERATELY NOT REFUTED, and ``kalshi_resolution_sweep``
    depends on that. Its ``RECENT_FINAL_SELECT_SQL`` screens on
    ``yes_bid = 0 AND yes_ask = 1`` precisely because that shape falls through to
    the last trade in the writer — it is how a stuck 99%/1% ladder is detected. An
    ask of 1.00 cannot be exceeded by any price, so this predicate is inert on the
    empty book by construction rather than by a special case, and
    ``test_empty_book_still_falls_through_to_the_last_trade_5121`` pins it.

    The bid arm is the ask arm's mirror (a live bid ABOVE the number prices it out
    the same way, since you could sell into that bid). It is a completion, not a
    measured repair: the writer only reaches rule 2 with a positive bid when the
    spread is >= 0.50, and production carries no such rows from that writer — the
    374 ``probability < yes_bid`` Kalshi rows that do exist have an ask
    distribution rule 1 could not have produced, so another writer owns them
    (filed separately, NOT fixed here).
    """
    if (
        yes_ask is not None
        and yes_ask > 0
        and price > yes_ask + BOOK_REFUTES_PRICE_EPSILON
    ):
        return True
    if (
        yes_bid is not None
        and yes_bid > 0
        and price < yes_bid - BOOK_REFUTES_PRICE_EPSILON
    ):
        return True
    return False


def lone_ask_on_empty_book_sql(alias: str) -> str:
    """The same rule as a SQL boolean over a ``futures_odds_snapshots`` alias.

    Returns an expression that is TRUE for exactly the rows
    :func:`is_lone_ask_on_empty_book` accepts **and that Kalshi wrote**.
    ``yes_bid``/``yes_ask`` are nullable, so the expression is written to
    evaluate to FALSE — never NULL — when the book is absent, which keeps it
    safe under ``NOT (...)``.

    WHY THE BOOKMAKER TERM IS IN HERE and not left to the caller (CERT-2508).
    The one caller, Phase 0c-repair, reads every source's snapshots and filters
    only on ``fm.status = 'resolved'``. Without the scoping this Kalshi book
    policy is applied to Polymarket, whose rule for the same columns is a
    different one (gotcha #19: wide spread → ``lastTradePrice``; no trade and no
    bid → skip). Measured on production over a 4-hour window, 14:35Z 2026-09-10:

        bookmaker    snapshots   with yes_bid   matching this predicate
        kalshi          95,401        95,398              0
        polymarket      20,150        15,876             23

    Kalshi is zero because the WRITE guard has refused this shape since
    2026-07-13 — the whole Kalshi population this module exists for is
    historical. So the unscoped expression was inert on the venue it was written
    for and live on the one it was not. The term lives here rather than at the
    call site because a predicate that is only correct when the caller remembers
    to add something is the bug, restored.

    ``bookmaker`` is NOT NULL, so adding it cannot make the expression NULL.
    """
    if not alias.isidentifier():
        raise ValueError(f"alias must be a bare SQL identifier, got {alias!r}")
    return (
        f"({alias}.bookmaker = '{KALSHI_BOOKMAKER}'"
        f" AND COALESCE({alias}.yes_bid, -1) = 0"
        f" AND COALESCE({alias}.last_price, 0) = 0"
        f" AND COALESCE({alias}.yes_ask, 0) > {ASK_ONLY_TRUSTED_MAX})"
    )
