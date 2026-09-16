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
    book_refutes_price,
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
    "price_refuted_by_live_book",
    "snapshot_price_is_unsupported",
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


def price_refuted_by_live_book(
    source: Optional[str],
    resolution_source: Optional[str],
    is_winner: Optional[bool],
    probability: Optional[float],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
) -> bool:
    """True when the row's own book prices out the price the row serves (#6532).

    WHAT A READER SAW. ``/events/15312074`` (Valencia v Real Sociedad, a fixture
    four days from kick-off) printed **"Relegated 99%"** for Real Sociedad under
    *Season context*, directly beneath that club's own record on the same card,
    **2-1-3**, six games into a twenty-club season. The same number again on
    ``/events/15312073`` and on ``/sport/soccer/laliga``, where the whole column is
    visible at once and sums to **8.24** in a league that relegates exactly three.
    Real Sociedad's row carries ``current_probability 0.99`` beside
    ``current_yes_ask 0.4900``: you can buy the outcome at 49c while we print 99%.

    THE ROW REFUTES ITSELF AND NO VENUE READ IS NEEDED, which is the test every
    arm of this module is built on. The price and the two book columns are three
    fields of ONE write — Real Sociedad's ``last_updated`` is a single timestamp
    for all three — so this is our stored value against another field of the same
    write, never our value against what the venue says today, a shape that invents
    a second writer and blames the market for moving.

    🔴 THE RULE IS NOT NEW AND IS NOT RE-DERIVED. :func:`book_refutes_price` is
    #5121's shipped predicate, written for and still used by
    ``_kalshi_yes_probability`` rule 2, carrying its own measured half-cent
    tolerance and its own empty-book carve-out (an ask of 1.00 cannot be exceeded,
    so the stuck 99%/1% ladder ``kalshi_resolution_sweep`` depends on falls through
    untouched). It guards the WRITE. Nothing guarded the READ — and as everywhere
    else in this module, the guard that stops a new fabrication is exactly what
    guarantees the old one survives: ``_kalshi_yes_probability`` returns ``None``
    for a refuted trade and the caller SKIPS the row rather than nulling it, so the
    book columns go on being kept current beside a price column that is frozen.

    WHY THE TWO SHIPPED ARMS ARE INERT HERE, both of them by their own rules.
    :func:`price_is_unsupported` asks "does a TRADE support this?" and
    ``is_lone_ask_on_empty_book`` needs ``yes_ask > 0.50``; Real Sociedad's ask is
    0.49, so the shape misses by one cent. And its first clause exempts any graded
    row — of the 19 priced legs on that market, 15 carry
    ``resolution_source='api_settlement'``, Real Sociedad among them, so the whole
    family is disarmed on the specimen before any price rule is reached.

    🔴 A GRADED ROW IS STILL EXEMPT — EXCEPT WHERE ITS OWN GRADE AND ITS OWN PRICE
    DISAGREE, and that carve-out is as narrow as the sentence it comes from. The
    other two arms exempt a graded row because "the number is a settlement value,
    not a quote", and that is right: settled means settled, withholding a result
    would pre-empt the settled-language ship (#4788, #5549, #5820), and this file
    must not start deleting results. But a settlement value is 0 or 1. A row whose
    grade says the outcome LOST while its price says 0.99, on a book offering it at
    0.49, is stating neither a settlement value nor a quote anyone will honour, and
    both of its own fields say so. So:

    * a graded WINNER is never touched, whatever the book says. 163 Polymarket and
      1 Kalshi leg sit above their own stale ask at exactly 1.0 — settled winners
      with a book nobody refreshed — and every one of them keeps its price.
    * a graded row with no verdict (``is_winner`` NULL beside a resolution source)
      is never touched either: ignorance about which way it went is not evidence.
    * a graded LOSER is asked the ASK arm only. Its number must be ~0, so a price
      the live bid prices out from BELOW is still the 0 its grade implies and is
      left alone — 110 Kalshi legs, almost all of them a settled 0.0000 beside a
      bid nobody cleared, which the symmetric form would have blanked. Deleting
      those is the exact harm the exemption exists to prevent.

    An UNGRADED row is a quote and gets the shipped predicate whole, both arms: a
    number the live book prices out is refuted whichever side prices it out.

    SCOPED TO KALSHI, DELIBERATELY, and this one does not port. Polymarket's rule
    for these columns is a different one (gotcha #19: a wide spread falls back to
    ``lastTradePrice``), so a Polymarket price legitimately sits above its own ask
    whenever the last trade did — the 385 ungraded Polymarket legs in that shape
    are the stale-trade question, which #5876's arm already answers on that venue
    with the newest snapshot rather than the book. Measured on production
    2026-09-16: 411 Kalshi legs on open markets are refuted here, 210 of them
    ungraded and 201 graded losers; the specimen's market contributes 3.

    WITHHOLDING, NEVER REWRITING. Serving the ask instead would be a number we
    invented, and ``calibration_probability`` coalesces to stored values (gotcha
    #144 / ruling 103), so an invented price becomes a forecast we are graded on.
    Nothing here mutates a stored price (gotcha #21).
    """
    if (source or "").strip().lower() != KALSHI_BOOKMAKER:
        return False
    if probability is None:
        return False
    if resolution_source is not None:
        if is_winner is not False:
            return False
        # A graded loser: the ask arm alone, for the reason above. Passing no bid
        # is how the shared predicate is asked half its question — it reads the
        # bid only to run the mirror arm, so `None` disables that arm exactly the
        # way an absent book does, with no second copy of the rule here.
        return book_refutes_price(None, yes_ask, float(probability))
    return book_refutes_price(yes_bid, yes_ask, float(probability))


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


def snapshot_price_is_unsupported(
    bookmaker: Optional[str],
    resolution_source: Optional[str],
    probability: Optional[float],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    last_price: Optional[float],
    *,
    is_winner: Optional[bool] = None,
) -> bool:
    """All three arms above, asked of ONE historical ``futures_odds_snapshots`` row (#5898).

    THE CHART IS THE THIRD RAIL AND IT KEPT THE NUMBER THE LADDER REFUSED.
    ``/futures/8641774`` withholds Ceará's price today — the table prints ``—``.
    ``/api/futures/8641774/history`` still returns Ceará's series with ``0.4700``
    as its last point, so checking that row's box draws a line ending at exactly
    the value the table just declined to state. Nine of the ten charted series on
    that page end on a refused value. Measured on production 2026-09-13 20:48Z.

    THE PREDICATE PORTS WITHOUT A NEW RULE, AND THAT IS NOT A CONVENIENCE — IT IS
    WHAT THE MODULE ALREADY ARGUES. ``midpoint_refuted_by_last_trade``'s case
    rests on the two numbers having been "written in the same microsecond … one
    write of ours against another field of the same write". That sentence is a
    statement about a SNAPSHOT ROW: ``probability``, ``yes_bid``, ``yes_ask`` and
    ``last_price`` are four columns of one insert. The current-price call site is
    the one that has to assemble them from two places (the outcome row plus a
    LATERAL into the newest snapshot); here they arrive together, already paired
    by the writer. So there is no second copy of a price rule and no second
    constant — the same two functions, handed the row they were reasoning about.

    KEYED ON THE SNAPSHOT'S OWN ``bookmaker``, NEVER ON ``market.source``. Both
    chart endpoints average every book's row at one timestamp into a single
    consensus point, and ``/multi-history`` merges outcomes ACROSS source markets
    on purpose. Screening by the market's source would take an honest sportsbook
    row down with a refuted Polymarket one at the same instant; screening by the
    row's own bookmaker drops the refuted contributor and lets the timestamp keep
    its honest ones. A point survives with a smaller, truer average rather than
    disappearing.

    ``has_trade_evidence`` IS ``last_price is not None`` HERE, AND THE GOTCHA #53
    DISTINCTION SURVIVES THE TRANSLATION. At the current-price call site the flag
    answers "did the snapshot read find a row at all", which is a fact about the
    query. For one row there is no such question — the row is the read — so the
    remaining question is the other one: did the venue tell us a trade price at
    this capture. NULL means it did not and the point is served exactly as it is
    today; a stored 0.0 means the venue said zero, which both arms already treat
    as evidence. The two are distinguished upstream by Polymarket's and Kalshi's
    writers, which is what makes reading them differently safe.

    THE THIRD ARM NEEDS NO TRADE AT ALL AND IS THE CHEAPEST OF THE THREE (#6532).
    :func:`price_refuted_by_live_book` reads ``probability`` against ``yes_bid``
    and ``yes_ask``, which on a snapshot are three columns of one insert — the
    tightest form of the same-write argument this whole docstring rests on. It is
    here, and not deferred to its own ship, because the specimen forces it: all
    three refuted legs of market 56775508 carry four charted points each inside
    the page's own 168-hour window and every one of those points is refuted, so a
    ladder printing ``—`` over a chart ending at 0.99 would be #5898's defect
    rebuilt by its own repair. Measured on production 2026-09-16 over the 411 legs
    this arm refuses today: 268 draw a series in that window, and 894 of their
    1,453 points are refused.

    ``is_winner`` IS KEYWORD-ONLY WITH A ``None`` DEFAULT, AND THAT DEFAULT FAILS
    OPEN. ``None`` is the "graded, verdict unknown" case, which
    :func:`price_refuted_by_live_book` exempts, so a caller that never learned
    about this argument keeps every point it serves today. Absence is not evidence
    here, for the reason it is not evidence anywhere else in this module.

    ``resolution_source`` IS THE OUTCOME'S, NOT THE ROW'S. Snapshots carry no
    grade, and both arms exempt a graded outcome for the reason they each state
    at length: once it is set the number is a settlement value and withholding it
    would delete a result. On this endpoint the exemption is load-bearing twice
    over — ``_apply_settled_winner_freeze`` resolves the graded champion's line to
    1.0 AFTER this filter runs, and a settled chart showing the completed journey
    is the standing ruling (#225 item 3, #232). A graded outcome keeps every
    point it has.

    MEASURED SERVED REACH, taken through the serving path rather than off the
    table, because on this defect class the table is an upper bound (the lesson
    #5968 cost). 30 markets sampled every 33rd from the 1,231 open Polymarket
    markets holding a fabricated-midpoint leg, each read at the page's own
    ``hours=168`` and each served point classified by its own row, 2026-09-13
    20:53Z:

        sampled markets serving a chart                       28
        ... carrying at least one refused point                7
        ... with a series ENDING on a refused point            7
        series: 116 total, 7 end on a refused value, 1 loses every point
        points:  348 refused of 1,780

    Two further markets were dropped from the sample because the admin
    db-query's 1,000-row cap truncated their classification; they are not counted
    either way. ONE series of 116 goes empty, which is the number that matters
    against this ship: it removes a fabricated segment and leaves a real curve —
    it does not blank charts. Where a series does lose every point it renders
    empty, which is notice 34's direction and what #5968 already does one surface
    over.

    THE KALSHI ARM IS MEASURED INERT ON THIS SURFACE TODAY AND SHIPS ANYWAY. The
    same sample over 30 open Kalshi markets (21 serving a chart, 57 series, 118
    points) refused NOTHING: #5611's twelve artists stopped being snapshotted in
    April, so they fall outside every window the chart serves. It is included
    because the ladder above the chart applies both arms, and a chart rule that
    said "Polymarket only" would be exactly the second copy of a price policy
    this module exists to prevent — the divergence would surface as a bug the
    first day a fossil gets re-snapshotted, which is how ``/multi-history`` came
    to lack the sparse-window widening its sibling has.
    """
    has_trade_evidence = last_price is not None
    if price_is_unsupported(
        bookmaker,
        resolution_source,
        yes_bid,
        yes_ask,
        last_price,
        has_trade_evidence=has_trade_evidence,
    ):
        return True
    if price_refuted_by_live_book(
        bookmaker,
        resolution_source,
        is_winner,
        probability,
        yes_bid,
        yes_ask,
    ):
        return True
    return midpoint_refuted_by_last_trade(
        bookmaker,
        resolution_source,
        probability,
        yes_bid,
        yes_ask,
        last_price,
        has_trade_evidence=has_trade_evidence,
    )
