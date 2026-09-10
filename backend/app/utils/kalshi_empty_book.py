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
