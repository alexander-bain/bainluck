"""An empty Polymarket book is not an opening — the shared predicate (#9083).

WHAT A READER SAW. ``/events/15319167`` (Phillies 1 – 12 Rays) led its props rail
with "Turner's 1+ hits + runs + rbis was marked 1% — and it hit". The 1% is the
stored ``opening_probability`` of ``futures_outcomes`` 236480965, promoted by
``backfill_winners`` Phase 0c-repair (``opening_source = 'first_snapshot'``) from
the only snapshot taken before first pitch:

    leg     probability   yes_bid   yes_ask   last_price
    Over       0.01        NULL      1.0000     0.0100
    Under      0.99        0.0000    NULL       0.9900

Nobody bids, and nobody offers below a dollar. Gotcha #19 sends a wide Polymarket
book to ``lastTradePrice``, so a 1c dust trade became the "price". The Under row
is the same book read from the other token (``complementary_book``), so it is the
same non-price at 0.99.

WHY THE KALSHI GUARD DID NOT CATCH IT. Phase 0c's only book guard is
:func:`app.utils.kalshi_empty_book.lone_ask_on_empty_book_sql`, scoped to Kalshi on
purpose (CERT-2508): Polymarket writes the same columns under a different policy,
so the Kalshi rule is the wrong rule for it. This module is Polymarket's rule,
scoped the same way, so neither venue's policy leaks onto the other.

THE RULE. A Polymarket snapshot is refused as an opening when its recorded book
quotes nothing: no bid above one tick AND no ask below one tick short of a dollar.
A missing side counts as the empty extreme on that side (bid NULL → 0, ask NULL →
1), because the writer records both sides from the same Gamma read, so a side it
recorded as absent was absent. At least ONE side must be recorded: a row with
neither is a snapshot from before CAL-P097 gave Under legs a book (493,415 of
them), and an absent column is not an absent book (gotcha #53).

THE TICK IS WHAT MAKES IT SYMMETRIC, AND THE PAIR NEEDS THAT. The Under's book is
``(1 - over_ask, 1 - over_bid)``. With a strict zero/one test, the production row
*Victor Bericoto Under* (bid 0.00 / ask 0.99) passes while its Over (bid 0.01 /
ask 1.00) would be judged separately, and the two legs of one book could split.
``bid <= TICK AND ask >= 1 - TICK`` maps onto itself under the flip, so a leg and
its twin always get the same answer.

MEASURED (production, 2026-09-27, every Polymarket leg on MLB games from the
previous 3 days with a ``first_snapshot`` opening, earliest snapshot before
``resolution_date``):

    book shape at capture       legs   mean opening   actually won
    lone ask (no bid)            549       0.052          9.8%
    lone bid (no ask)            413       0.942         89.8%
    EMPTY (this rule)             49       0.540         53.1%
    two-sided                      5       0.491         60.0%

The empty row's mean is 0.5 by construction (both legs of each pair). Split by leg,
it is what the specimen shows: 21 Overs stated at 0.01 won 3 times (14%), and 24
Unders stated at 0.99 won 21 (87.5%). Of the 49, 45 are 1c/99c dust-trade pairs.
The other four are named, so what this costs is on the record: Cubs team total
O/U 3.5 (0.58/0.42 from a real last trade on a book that has since emptied; this
rule withdraws it), Carlos Jorge total bases 0.50 (no trade at all: a midpoint),
and Yankees O/U 1.5 at 0.995 (no trade, no bid).

Lone asks and lone bids are NOT refused. A lone bid is a price somebody will pay
and grades close to its stated level; a Polymarket lone ask grades 5.2% against
9.8%, which is not this defect, and it is left alone.
"""

from __future__ import annotations

from typing import Optional

#: ``futures_odds_snapshots.bookmaker`` for the venue this rule is about.
POLYMARKET_BOOKMAKER = "polymarket"

#: One tick of the cent grid these legs trade on. A 1c bid is the smallest bid a
#: book can show, and a 99c ask the largest ask short of a dollar. The bound on
#: each side is this tick, so the pair stays symmetric under ``complementary_book``.
EMPTY_BOOK_TICK = 0.01

#: ``yes_bid``/``yes_ask`` are Numeric(5,4); 4dp is exact for them, and rounding
#: stops ``1 - 0.99 = 0.010000000000000009`` escaping a 0.01 bound in Python the
#: way it cannot in the column.
_BOOK_DECIMALS = 4


def is_empty_polymarket_book(
    yes_bid: Optional[float],
    yes_ask: Optional[float],
) -> bool:
    """True when this recorded Polymarket book quotes nothing on either side.

    All arguments are decimal probabilities (0-1) as ``futures_odds_snapshots``
    stores them. Both ``None`` → False: no book was recorded, so this predicate
    knows nothing about the row.
    """
    if yes_bid is None and yes_ask is None:
        return False
    bid = 0.0 if yes_bid is None else round(float(yes_bid), _BOOK_DECIMALS)
    ask = 1.0 if yes_ask is None else round(float(yes_ask), _BOOK_DECIMALS)
    return bid <= EMPTY_BOOK_TICK and ask >= round(1 - EMPTY_BOOK_TICK, _BOOK_DECIMALS)


def empty_polymarket_book_sql(alias: str) -> str:
    """The same rule as a SQL boolean over a ``futures_odds_snapshots`` alias.

    TRUE for exactly the rows :func:`is_empty_polymarket_book` accepts **and that
    Polymarket wrote**. Never NULL (every nullable column is COALESCEd, and
    ``bookmaker`` is NOT NULL), so it is safe under ``NOT (...)``: a NULL here would
    silently drop every snapshot from Phase 0c's lateral.

    The bookmaker term lives here, not at the call site, for CERT-2508's reason: a
    predicate that is only right when the caller remembers to scope it is the bug.
    """
    if not alias.isidentifier():
        raise ValueError(f"alias must be a bare SQL identifier, got {alias!r}")
    return (
        f"({alias}.bookmaker = '{POLYMARKET_BOOKMAKER}'"
        f" AND ({alias}.yes_bid IS NOT NULL OR {alias}.yes_ask IS NOT NULL)"
        f" AND COALESCE({alias}.yes_bid, 0) <= {EMPTY_BOOK_TICK}"
        f" AND COALESCE({alias}.yes_ask, 1) >= {round(1 - EMPTY_BOOK_TICK, _BOOK_DECIMALS)})"
    )
