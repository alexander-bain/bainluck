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

THAT POLYMARKET SHIP IS #5876, AND IT IS THE SECOND HALF OF THIS MODULE. What a
reader saw: ``/futures/8641774`` (*Brazil Série B: Winner*) printed SIXTEEN of
twenty clubs at 45–50% each under a column header reading *LATEST*, a table
summing to roughly 700%. The stored value is ``(bid+ask)/2`` to five decimal
places on a book 0.90–0.98 wide, written 2026-07-21 and never rewritten since —
``is_fabricated_midpoint`` refuses that shape today, and a refusal is a SKIP, so
the guard that stops a new fabrication is exactly what guarantees the old one
survives. Same mechanism as the Kalshi half above, one venue over.

THE KALSHI PREDICATE DOES NOT PORT, AND THAT WAS MEASURED RATHER THAN ASSUMED.
These legs have a bid (0.002) and they have trades, so ``is_lone_ask_on_empty_book``
misses on both of its terms. Worse, the tempting screen — "has this outcome ever
traded near its served price?" — is actively wrong here: ``max(last_price)`` over
one outcome's 2,386 snapshots reads 0.92–0.96 and passes, while the NEWEST
snapshot reads 0.0040. The page says Ceará 47%; the last trade said 0.4%. So the
Polymarket arm is built on a different pair: ``is_fabricated_midpoint`` for the
shape, and the NEWEST snapshot's ``last_price`` as DISCONFIRMATION.

THE ROW REFUTES ITSELF, WHICH IS WHY NO GROUND TRUTH IS NEEDED. On all fifteen
specimen legs the disconfirming snapshot was captured in the SAME MICROSECOND as
the frozen price (``2026-07-21 17:16:33``): at the instant we wrote 0.4895 as
Sport's probability, the venue's own last trade on that outcome was 0.0100. This
is not our number against today's venue read — a comparison that would invent a
second writer — it is one write of ours against another field of the same write.

MEASURED ON PRODUCTION 2026-09-13, and measured on the PAYLOAD rather than the
row, because on this defect class the row is an upper bound and not a reach:

    screen                                              legs   markets
    fabricated midpoint, open, ungraded, Polymarket     3,898    1,361
    ... newest snapshot DISCONFIRMS the served price      664      379
    ... and `/api/futures/{id}` actually serves the leg    585      344

All 379 candidate payloads were fetched, 379/379, zero unresolved. The gap
between 664 and 585 is legs no reader can reach; it is not claimed as a fix.
"""

from __future__ import annotations

from typing import Optional

from app.utils.feed_market_quality import is_fabricated_midpoint
from app.utils.kalshi_empty_book import (
    KALSHI_BOOKMAKER,
    is_lone_ask_on_empty_book,
)

#: The bookmaker string the Polymarket futures writers stamp on every snapshot
#: (``app/tasks/polymarket.py``, four call sites) and the ``source`` a Polymarket
#: futures market carries. One spelling, named once.
POLYMARKET_BOOKMAKER = "polymarket"

__all__ = [
    "POLYMARKET_BOOKMAKER",
    "WITHHELD_PRICE_FIELDS",
    "midpoint_refuted_by_last_trade",
    "needs_trade_disconfirmation",
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


#: What "the last trade supports the served price" means, and it is anchored to
#: the READER rather than chosen. The detail page prints whole percents, so two
#: numbers that round to the same percent are the same number to the person
#: looking at it: a trade supports the printed value exactly when it prints as
#: that value. Half a point is that rounding.
#:
#: It is deliberately NOT fitted to the population. Measured on production
#: 2026-09-13 across the 678 fabricated-midpoint legs that carry a newest trade,
#: |trade − served| has NO natural cliff — 15 legs under 0.005, a thin smear of
#: 85 between 0.005 and 0.10, then 578 at 0.10 or worse. Any threshold inside
#: that smear would be tuned, and the honest way to pick one is to say what the
#: number MEANS on the surface it defends. The bulk of the defect sits two orders
#: of magnitude away from the boundary, so nothing here turns on its exact value.
_DISPLAY_ROUNDING = 0.005


def needs_trade_disconfirmation(
    source: Optional[str],
    resolution_source: Optional[str],
    probability: Optional[float],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
) -> bool:
    """True if this Polymarket row is a fabricated midpoint a trade read can refute.

    The screen half of the Polymarket arm, and the mirror of
    :func:`needs_trade_evidence`: everything it reads is on the outcome row
    already, so a market holding no candidate never touches the snapshot table.

    ``is_fabricated_midpoint`` is IMPORTED, not restated. It is the shipped
    answer to "was this price manufactured by averaging a spread nobody will
    trade inside", it carries its own measured 0.20 constant, and #1574 already
    defends it on the feed. Re-deriving the shape test here would be a second
    copy of a price rule in the codebase, which is the thing this module exists
    to prevent.

    A GRADED ROW IS NEVER A CANDIDATE, for the reason
    :func:`needs_trade_evidence` gives at length: once ``resolution_source`` is
    set the number is a settlement value, not a quote, and withholding it would
    delete a result and pre-empt the settled-language ship (#4788, #5549, #5820).
    """
    if (source or "").strip().lower() != POLYMARKET_BOOKMAKER:
        return False
    if resolution_source is not None:
        return False
    return is_fabricated_midpoint(probability, yes_bid, yes_ask)


def midpoint_refuted_by_last_trade(
    source: Optional[str],
    resolution_source: Optional[str],
    probability: Optional[float],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    last_price: Optional[float],
    *,
    has_trade_evidence: bool,
) -> bool:
    """True when the venue's newest recorded trade refutes the served midpoint.

    ``has_trade_evidence`` is the caller's answer to "did the snapshot read find
    a row", and it is separate from ``last_price`` for the reason gotcha #53
    states and :func:`price_is_unsupported` repeats: an absent snapshot and a
    snapshot reading zero are different answers to different questions. Absence
    FAILS OPEN and the price is served exactly as it is today.

    That fail-open is the majority of the raw shape, not a corner, and it is
    stated as a cost rather than buried. Measured on production 2026-09-13 over
    the 3,898 fabricated-midpoint legs on open Polymarket markets: 3,220 carry a
    snapshot whose ``last_price`` is NULL and are therefore left alone by this
    rule. Their prices may well be fabricated too — but "we never recorded a
    trade for this outcome" is not evidence that no trade exists, and inventing
    that inference is how a withholding rule starts deleting honest longshots.

    A ZERO ``last_price`` IS EVIDENCE AND DOES REFUTE. Polymarket's writers
    assign ``last_trade_price`` straight through (``app/tasks/polymarket.py``),
    so a NULL means the venue told us nothing and a stored 0.0 means the venue
    told us zero — the two cases are already distinguished upstream, which is
    what makes it safe to read them differently here. 46 legs on 5 markets are
    in that state, every one of them serving exactly 0.5000 off a 0.0/1.0 book:
    the manufactured coin-flip, which is the Kalshi half's twelve artists in a
    Polymarket costume.

    NOT A COMPARISON AGAINST A LIVE VENUE READ. Both numbers come out of our own
    database, and on the specimen they were written in the same microsecond, so
    this cannot drift into "our stored value versus what the venue says today" —
    a shape that invents a second writer and blames the market for moving.
    """
    if not needs_trade_disconfirmation(
        source, resolution_source, probability, yes_bid, yes_ask
    ):
        return False
    if not has_trade_evidence or last_price is None or probability is None:
        return False
    return abs(float(last_price) - float(probability)) >= _DISPLAY_ROUNDING
