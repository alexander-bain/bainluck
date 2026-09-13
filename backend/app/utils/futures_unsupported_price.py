"""A futures price no book and no trade supports is not served (#5611).

WHAT A READER SAW. ``/futures/109279`` ("Who will release a new song this
year?") printed twelve artists at ``LATEST 100%`` — Don Toliver, Charlie Puth,
J Balvin, BLACKPINK, Kodak Black, Rauw Alejandro and six more, each headed by a
column reading *Latest*. Every one of those rows carries ``yes_bid 0.0000 /
yes_ask 1.0000``: nobody is bidding anything and nobody is offering below
certainty. Their newest ``futures_odds_snapshots`` row carries
``last_price 0.0000`` — the market has never traded — and their
``current_probability`` was last written in **April**. The page took a
five-month-old fossil, put a *Latest* header on it, and told the reader a man
was certain to release a song.

THE RULE IS NOT NEW AND IS NOT REDERIVED HERE. ``is_lone_ask_on_empty_book``
(``app.utils.kalshi_empty_book``) already decides this exact question, was
measured over 34,281 resolved Kalshi legs, and is the predicate #5611 names.
This module is the CALL-SITE POLICY around it — which rows may be asked, and
which fields fall when the answer is yes — so that the futures detail
serializer contains no second copy of a price rule.

WHY NOT ``is_empty_book_midpoint``, the #5247 helper that already ships for
event pages, which #5611 names as the prior art. Measured on production
2026-09-13 over the 443 open Kalshi legs that are ungraded, quote an empty book
and have never traded:

    predicate                              legs   mean served price
    #5247 midpoint rule catches              63        0.496
    #5247 midpoint rule MISSES              380        0.988

That rule requires the served price to sit ON the book's midpoint, and reasons
that a price far from the midpoint "got that price from a real trade (Kalshi
falls back to ``last_price`` on a wide book)". For this population the
snapshots refute that premise: the price is far from the midpoint AND
``last_price`` is 0. It is not a trade — it is a value frozen before the
poller's own write guard existed. So porting the midpoint helper here would fix
the 63 honest-looking coin-flips and leave the 380 loudest rows on the page.
The midpoint helper is not wrong on its own surface and is not touched; it is
simply blind to a fossil, because it is given no trade column to look at.

THE POLLER ALREADY REFUSES TO WRITE THIS SHAPE, WHICH IS WHY IT SURVIVES.
``_kalshi_yes_probability`` rule 4 returns ``None`` for a one-sided book with no
trade, and the caller then SKIPS the row rather than nulling it. A skip
preserves whatever was there, so the guard that stops a new fabrication also
guarantees the old one is never overwritten. 801 of these rows were touched by
the poller within six hours of the measurement — their book columns are being
kept current while the price column stays frozen — so the row refutes itself:
an empty book beside a confident price, written months apart.

READ-SIDE ONLY. Nothing here mutates a stored price (gotcha #21); the serializer
declines to publish one. Withholding, never rewriting: a rescaled or inferred
price would be a number we invented, and ``calibration_probability`` coalesces
to stored values (gotcha #144 / ruling 103), so an invented price becomes a
forecast we are graded on.

SCOPED TO KALSHI, DELIBERATELY. ``kalshi_empty_book``'s own SQL form carries the
bookmaker term and its docstring says why: Polymarket's rule for these same
columns is a different one (gotcha #19 — wide spread falls back to
``lastTradePrice``; no trade and no bid is skipped). 378 Polymarket legs on 56
open markets match the raw bid/ask shape and are deliberately left alone; a
Polymarket ruling is its own ship, not a silent rider on this one.
"""

from __future__ import annotations

from typing import Optional

from app.utils.kalshi_empty_book import (
    ASK_ONLY_TRUSTED_MAX,
    KALSHI_BOOKMAKER,
    is_lone_ask_on_empty_book,
)

__all__ = [
    "WITHHELD_PRICE_FIELDS",
    "needs_trade_evidence",
    "price_is_unsupported",
]

#: Every field that is a restatement of the refused price. They fall together or
#: the refusal is cosmetic: ``current_american_odds`` is the same number in
#: another notation, and ``probability_change_24h`` is a delta measured FROM the
#: value being withheld — publishing "up 50.0 pts" while refusing to say up to
#: what is the #5539 mistake in a second costume.
WITHHELD_PRICE_FIELDS = (
    "probability",
    "american_odds",
    "probability_change_24h",
)


def needs_trade_evidence(
    source: Optional[str],
    resolution_source: Optional[str],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
) -> bool:
    """True if this row could be an unsupported price and a trade read decides it.

    Everything here is on the outcome row already, so the serializer can settle
    the overwhelming majority of outcomes without touching the snapshot table:
    only rows that pass this ask for trade evidence. On a market with no
    candidates the price-support read is skipped entirely.

    A GRADED ROW IS NEVER A CANDIDATE, and this is a scope boundary rather than
    an optimisation. Once ``resolution_source`` is set, the number is a
    settlement value, not a quote — ``settled_price_values`` writes it when the
    venue answers — and what to print for it is the settled-language question
    (#4788, #5549, #5820), owned elsewhere and already shipping a verdict on the
    wire. Withholding here would quietly pre-empt that answer and delete a
    result. Measured: 4,444 of the 6,918 open Kalshi legs quoting an empty book
    are graded, so this clause is the majority of the raw shape, not a corner.
    """
    if (source or "").strip().lower() != KALSHI_BOOKMAKER:
        return False
    if resolution_source is not None:
        return False
    if yes_bid is None or yes_ask is None:
        return False
    # The cheap half of `is_lone_ask_on_empty_book`, which is the whole of it
    # apart from the trade term. Stated as a delegation, not a re-implementation:
    # passing a last_price of 0 asks that predicate the bid/ask half of its own
    # question, so this can never drift away from the rule it screens for.
    return is_lone_ask_on_empty_book(yes_bid, yes_ask, 0.0)


def price_is_unsupported(
    source: Optional[str],
    resolution_source: Optional[str],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    last_price: Optional[float],
    *,
    has_trade_evidence: bool,
) -> bool:
    """True when no current quote and no recorded trade supports the served price.

    ``has_trade_evidence`` is the caller's answer to "did the snapshot read
    actually find a row for this outcome", and it is separate from
    ``last_price`` on purpose. An absent snapshot and a snapshot reading zero are
    different answers to different questions (gotcha #53): the first is "we did
    not look, or have never recorded this outcome", the second is "we looked and
    the market has never traded". Only the second is evidence, so the absent case
    FAILS OPEN and the price is served exactly as it is today.

    Measured on production 2026-09-13: of the 2,474 ungraded open Kalshi legs
    quoting an empty book, every one had a snapshot carrying a non-null
    ``last_price`` — 2,031 positive, 443 zero — so fail-open costs nothing today
    and is the honest default the day it does not.

    The 2,031 with a positive ``last_price`` are NOT withheld. That is the
    shipped predicate's rule 2 ("trade evidence beats a wide book") and it is
    deliberately left standing: whether a real trade goes stale is the freshness
    question (#5314, #5781), a different ship with a different answer, and
    folding it in here would be this lane re-deriving a measured policy on a
    hunch.
    """
    if not needs_trade_evidence(source, resolution_source, yes_bid, yes_ask):
        return False
    if not has_trade_evidence:
        return False
    return is_lone_ask_on_empty_book(yes_bid, yes_ask, last_price)


# Re-exported so a reader of this module can see the bound the rule turns on
# without opening a second file, and so a test can assert the two agree.
_ASK_ONLY_TRUSTED_MAX = ASK_ONLY_TRUSTED_MAX
