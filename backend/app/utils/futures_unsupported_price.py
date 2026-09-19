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

from typing import Iterable, Optional

from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    book_bounds_nothing,
    is_fabricated_midpoint,
)
from app.utils.field_opening_coherence import MIN_FIELD_LEGS
from app.utils.kalshi_empty_book import (
    KALSHI_BOOKMAKER,
    book_refutes_price,
    is_lone_ask_in_exclusive_field,
    is_lone_ask_on_empty_book,
)
from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE

#: The outcome relations that PROVE a single-winner partition (#6846). Mirrors
#: ``app.tasks.precompute_calibration.EXCLUSIVITY_PROVED_RELATIONS``, which is the
#: canonical list and cannot be imported here: it lives in a 7,700-line Celery
#: task module that the web dyno does not load today (verified — ``app.main``
#: imports leave ``precompute_calibration`` out of ``sys.modules``), and pulling
#: it onto the futures serve path to read one frozenset would drag calibration's
#: whole dependency tree into every request. D45 also forbids this lane editing
#: that file to lift the symbol out.
#:
#: A copied policy drifts, which this codebase says in its own words
#: (``kalshi_empty_book``: "a price policy that exists twice drifts"). So the two
#: are pinned together by ``tests/test_ask_only_exclusive_field_6846.py``, which
#: imports BOTH and asserts they agree across the classifier's full verdict
#: matrix — the same protection ``ASK_ONLY_TRUSTED_MAX`` gets from being bound to
#: rule 3 by a test rather than by an import.
EXCLUSIVITY_PROVED_RELATIONS = frozenset({"competitors", "exclusive_ranges"})

#: Every ``resolution_source`` that is a RETRACTION rather than a verdict (#6876).
#: Imported, never restated: ``kalshi_fabricated_loss`` already names the one
#: spelling, and ``resolution_authority`` already classifies it — tier 1 TERMINAL,
#: "a RETRACTION, not a grade ... It asserts no winner, so it is structurally
#: no-winner and calibration-truth INELIGIBLE".
#:
#: The set has exactly one member and the other seven tier-1 sources are
#: deliberately NOT in it. ``did_not_play``, ``withdrew``, ``all_losers``,
#: ``pass2_loser`` and ``date_passed`` all DECLARE a loss and ``clean_resolution``
#: is a soft close - every one of them is a settlement value of 0, which is the
#: thing the grade exemption exists to protect. Only ``ungradeable_result`` says
#: "we asked and there is no result", and only it is therefore still a quote.
#: Keying on the named retraction rather than on a property (tier, calibration
#: eligibility) is deliberate: those answer "how good is this grade", and the
#: question here is "is there a grade at all".
RETRACTED_GRADE_SOURCES = frozenset({RETRACTION_SOURCE})

#: The highest probability that TWO legs of a one-winner field can share (#7059).
#:
#: DERIVED, NOT TUNED, in the same style as
#: ``field_opening_coherence.FIELD_MEAN_CEILING`` (``1/3`` — "the largest mean any
#: honest field of three or more can carry"). Exactly one leg of a single-winner
#: partition wins, so the true probabilities sum to 1 and at most one of them can
#: exceed ``1/2``. Two legs each strictly above this value is not an overstatement
#: to be judged against a measured band — it is an arithmetic impossibility, and
#: no overround story reaches it: vig inflates a column proportionally, so seating
#: a SECOND leg above 0.5 takes roughly a doubling, not a margin.
#:
#: The comparison is STRICT. Two legs at exactly 0.50 sum to exactly 1, which is a
#: coin flip and not a contradiction; only ``> 0.50`` on two legs is impossible.
SECOND_FAVOURITE_CEILING = 0.5

#: The bookmaker string the Polymarket futures writers stamp on every snapshot
#: (``app/tasks/polymarket.py``, four call sites) and the ``source`` a Polymarket
#: futures market carries. One spelling, named once.
POLYMARKET_BOOKMAKER = "polymarket"

#: The two venues whose midpoint the trade arm can refute, and the ONLY two
#: whose writers record a ``last_price`` at all (#7222). Named as a set so the
#: screen and the snapshot read below cannot disagree about who is in scope —
#: the bug this ship fixes is precisely a predicate and a query that named
#: different populations.
MIDPOINT_TRADE_SOURCES = frozenset({POLYMARKET_BOOKMAKER, KALSHI_BOOKMAKER})

__all__ = [
    "EXCLUSIVITY_PROVED_RELATIONS",
    "MIDPOINT_TRADE_SOURCES",
    "POLYMARKET_BOOKMAKER",
    "RETRACTED_GRADE_SOURCES",
    "SECOND_FAVOURITE_CEILING",
    "WITHHELD_PRICE_FIELDS",
    "field_names_two_favourites",
    "market_is_proved_exclusive_field",
    "row_carries_a_verdict",
    "midpoint_refuted_by_last_trade",
    "needs_trade_disconfirmation",
    "needs_trade_evidence",
    "price_is_unlocated_in_broken_field",
    "price_is_unsupported",
    "price_refuted_by_live_book",
    "snapshot_price_is_unsupported",
]


def row_carries_a_verdict(resolution_source: Optional[str]) -> bool:
    """True when this ``resolution_source`` means a result was actually declared (#6876).

    THE GRADE EXEMPTIONS IN THIS FILE ASK THIS QUESTION AND USED TO SPELL IT
    ``resolution_source is not None``. That spelling is right for every source but
    one, and the one it is wrong about is the second-largest source on the very
    population those exemptions screen.

    WHAT A READER SAW. ``/futures/52755817`` ("2026 Pro Basketball Cup Champion")
    printed **eight teams at 29%** - Portland, Sacramento, Brooklyn, Chicago, the
    Clippers, Memphis and Milwaukee tied behind Oklahoma City's 30%, ranked 2
    through 9 by nothing - over a 30-team single-winner column summing to **489%**,
    with ``prices_withheld: 0`` and a Probability Trend drawing three flat
    overlapping lines because they are the same number. Seven of those eight have
    never traded: ``current_yes_bid 0.0000 / current_yes_ask 0.2900 / newest Kalshi
    snapshot last_price 0.0000``. The market resolves **2027-01-31**.

    WHY EVERY SHIPPED RAIL MISSED IT. The market's shape is PROVED exclusive
    (``field / exhaustive / expected_winners 1 / competitors``), so #6846's
    widening applies and the ask bound is dropped - but every leg carries
    ``resolution_source = 'ungradeable_result'``, and :func:`needs_trade_evidence`
    returned False at its grade clause before the field term was ever reached. The
    exemption written to protect verdicts was claimed by rows that have none.

    ``ungradeable_result`` IS A RETRACTION, AND THIS CODEBASE ALREADY SAYS SO in
    three places that predate this function. ``resolution_authority`` classifies it
    tier 1 TERMINAL with the words "a RETRACTION, not a grade ... It asserts no
    winner, so it is structurally no-winner and calibration-truth INELIGIBLE";
    ``routes/league_futures.py`` repeats "``ungradeable_result`` is a RETRACTION";
    ``routes/events.py`` keeps it OUT of the verdict set and carries a tier test
    that exists to hold it out. It is the grader recording that it could not grade.
    There is no result to delete and no settled-language answer (#4788, #5549,
    #5820) to pre-empt, because the row renders no verdict today - that is what the
    retraction means. The number beside it is a live quote and must face the price
    rails like any other quote.

    MEASURED, production 2026-09-18. Open Kalshi legs quoting an ask-only book
    (``current_yes_bid = 0``, ``ask > 0``, a price served), by what sits in
    ``resolution_source``::

        NULL (rail runs - correct)                     12,656 legs / 1,448 markets
        ungradeable_result (rail disarmed by this bug) 10,759 legs /   999 markets
        api_settlement (real verdict - stays exempt)    6,111 legs / 1,106 markets
        clean_resolution / all_losers / pass2_loser        109 legs /    28 markets

    Of the 10,759, those that also pass a bound term are 8,112 legs / 558 markets
    (proved field) and 265 legs / 55 markets (standalone, ``ask > 0.50``). Replaying
    the WHOLE predicate including the trade read, on a 1-in-10 sample of those: 255
    of 820 proved-field legs are withheld (31%, 131 markets) and **0 of 31**
    standalone legs are. Two thirds keep their number because they carry a real
    recorded trade, which is rule 2 ("trade evidence beats a wide book") doing
    exactly its job. On the specimen, 10 of the 14 ask-only legs go blank and four
    keep their price - the seven-way 29% tie collapses to the one leg somebody
    traded at 29.

    FAILS CLOSED, WHICH FOR A RULE THAT WITHHOLDS MEANS "KEEP THE EXEMPTION". The
    test is written as a denylist of one rather than an allowlist of the seven known
    verdict sources, deliberately: a source this file has never heard of - a new
    grader, a rail added after this was written - reads as a verdict and keeps
    today's exemption, so the only row this change can newly blank is one carrying
    the single source the codebase already calls a retraction. An allowlist would
    silently start withholding on every future source the day it shipped, which is
    the opposite of the direction a withholding rule should guess in.
    ``resolution_authority.KNOWN_SOURCES`` is the completeness guard for that space
    and it is not this function's job to duplicate it.
    """
    if resolution_source is None:
        return False
    return resolution_source not in RETRACTED_GRADE_SOURCES


def market_is_proved_exclusive_field(
    market_type: Optional[str],
    market_metadata: Optional[dict],
) -> bool:
    """True when the classifier PROVED this market is a single-winner partition (#6846).

    Evidence comes from the persisted shape classifier
    (``market_metadata->'shape'``, Queue #260 semantics v2) and never from
    ``futures_markets.mutually_exclusive``. That column DEFAULTS TO TRUE and is
    set for Yes/No claims and two-competitor duels alike, so it is not evidence
    of anything — the finding ``precompute_calibration`` recorded when its own
    census showed the default-true gate admitting 51,424 markets whose relation
    the classifier explicitly declined to resolve and 27,958 cumulative-threshold
    ladders whose rungs co-win (gotcha #17).

    Four conditions, all required, mirroring
    ``precompute_calibration.market_exclusivity_is_proved``:

      * ``market_type == 'field'`` — the ">2 competitors, one wins" verdict,
      * ``shape.exhaustive`` is true — only set when the SOURCE proves it,
      * ``shape.expected_winners == 1`` — not a Top-N or participation contract,
      * ``shape.outcome_relation`` is an exclusive relation — never
        ``cumulative_thresholds``, ``independent_participation`` or ``unknown``.

    FAILS CLOSED, which is the direction that matters for a rule that withholds.
    Absent metadata, an unparsed shape, an unrecognised relation or a classifier
    that declined all return False, and the leg is served exactly as it is today.
    The refusal only ever fires where the partition is proved.

    Values may arrive from JSONB as native types or as strings, so ``'true'`` and
    ``'1'`` are accepted alongside ``True`` and ``1`` — the same coercion the
    canonical helper does, for the same reason.
    """
    if market_type != "field":
        return False
    if not isinstance(market_metadata, dict):
        return False
    shape = market_metadata.get("shape")
    if not isinstance(shape, dict):
        return False
    if str(shape.get("exhaustive")).strip().lower() != "true":
        return False
    if str(shape.get("expected_winners")).strip() != "1":
        return False
    return (shape.get("outcome_relation") or "") in EXCLUSIVITY_PROVED_RELATIONS


#: Every field that is a restatement of the refused price. They fall together or
#: the refusal is cosmetic: ``current_american_odds`` is the same number in
#: another notation, and ``probability_change_24h`` is a delta measured FROM the
#: value being withheld — publishing "up 50.0 pts" while refusing to say up to
#: what is the #5539 mistake in a second costume.
#:
#: THE TUPLE IS KEYED ON PRESENCE, SO IT COVERS A FIELD A PAYLOAD GAINS LATER —
#: BUT NOT ONE IT SPELLS DIFFERENTLY. #6993's browse/faceted arm is that case:
#: both serve the 24h delta under the key ``movement``, so a presence-keyed loop
#: over the three names above walked straight past it and would have served
#: ``{"probability": null, "movement": 0.5}`` — the withheld number's own delta,
#: which is the second costume this comment already warns about. It is listed
#: here rather than nulled at those two call sites so the set of "spellings of
#: the refused price" stays in one place; presence-keying means no existing
#: caller changes behaviour by its addition.
WITHHELD_PRICE_FIELDS = (
    "probability",
    "american_odds",
    "probability_change_24h",
    "movement",
)


def needs_trade_evidence(
    source: Optional[str],
    resolution_source: Optional[str],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    *,
    in_exclusive_field: bool = False,
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

    #6876 NARROWS "GRADED" TO "CARRIES A VERDICT" AND CHANGES NOTHING ELSE. The
    clause above is right about every source that declares a result and wrong about
    the one that retracts one: ``ungradeable_result`` asserts no winner, so the
    number beside it is still a quote. :func:`row_carries_a_verdict` holds that
    distinction, with the measurement and the reader-visible cost.
    """
    if (source or "").strip().lower() != KALSHI_BOOKMAKER:
        return False
    if row_carries_a_verdict(resolution_source):
        return False
    if yes_bid is None or yes_ask is None:
        return False
    # The cheap half of the ask-only rules, which is the whole of them apart from
    # the trade term. Stated as a delegation, not a re-implementation: passing a
    # last_price of 0 asks the predicate the bid/ask half of its own question, so
    # this can never drift away from the rule it screens for.
    #
    # #6846: `in_exclusive_field` is the caller's answer to a question about the
    # MARKET, not about this row, and it is a keyword defaulting to False so every
    # existing caller keeps the behaviour it has today. Inside a PROVED
    # single-winner partition the ask bound is dropped — an ask-only book states
    # an upper bound, and a field's column is read as a distribution. Only the
    # BOUND changes; the grade exemption, the venue scope and the book shape are
    # identical in both frames. The argument and its measurement live on
    # `is_lone_ask_in_exclusive_field`.
    if in_exclusive_field:
        return is_lone_ask_in_exclusive_field(yes_bid, yes_ask, 0.0)
    return is_lone_ask_on_empty_book(yes_bid, yes_ask, 0.0)


def price_is_unsupported(
    source: Optional[str],
    resolution_source: Optional[str],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
    last_price: Optional[float],
    *,
    has_trade_evidence: bool,
    in_exclusive_field: bool = False,
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
    if not needs_trade_evidence(
        source,
        resolution_source,
        yes_bid,
        yes_ask,
        in_exclusive_field=in_exclusive_field,
    ):
        return False
    if not has_trade_evidence:
        return False
    # #6846. Both terms carry the same frame or the screen and the verdict
    # disagree: the field form would admit a leg the standalone form then
    # acquits, and the row would be counted as a candidate and served anyway.
    if in_exclusive_field:
        return is_lone_ask_in_exclusive_field(yes_bid, yes_ask, last_price)
    return is_lone_ask_on_empty_book(yes_bid, yes_ask, last_price)


def field_names_two_favourites(
    probabilities: "Iterable[Optional[float]]",
) -> bool:
    """True when this column names two favourites, which a one-winner field cannot (#7059).

    ``probabilities`` is one entry per leg the surface intends to SHOW, in any
    order. ``None`` entries are legs carrying no price — already withheld, or
    never priced — and are ignored rather than counted as zero, for
    ``classify_field_openings``' reason and gotcha #53's: "nobody is publishing a
    price" is not "the price is 0". The caller passes the list it will actually
    print, because that is the set whose coherence the page is claiming.

    WHY A COUNT AND NOT A SUM. The sum is the obvious test and it cannot see this
    defect. ``/api/futures/2951423`` serves sixteen legs summing to **2.995** with
    a mean of **0.187**, so ``field_opening_coherence``'s measured pair — sum above
    3.0 AND mean at or above 0.4 — spares it on the mean, and would spare it more
    comfortably the more honest longshots the field carries. Twelve of those legs
    are real 1% prices, and they are what dilutes the mean below the ceiling. That
    is not a ceiling set too high; it is a ceiling doing its job, protecting large
    fields whose sums drift for honest reasons (staggered per-leg capture, a
    100-leg board). latency/578 hit the identical dilution on #6996 and reached the
    identical conclusion from the other side: the answer is a COUNT, because adding
    honest longshots cannot change how many legs sit above a half.

    THAT SIBLING COUNT NOW SHIPS AND IS DELIBERATELY NOT REUSED. #6996 landed
    ``MAX_CERTAIN_LEGS = 1`` at ``CERTAIN_LEG_PROBABILITY = 0.999`` in
    ``field_opening_coherence`` — the same arithmetic in the same shape, and the
    reason this rule is phrased as a count rather than argued from first principles.
    It cannot answer here for two independent reasons: it reads
    ``opening_probability`` where this reads the current price, and its bound is
    CERTAINTY, which the specimen never reaches — 0.93 is the highest leg on the
    belt. Two legs at 0.93 and 0.87 are exactly as impossible as two at 1.0 and
    neither is certain, so the bound forced here is the one two legs can SHARE, a
    half, not the one a single leg cannot exceed.

    WHY IT IS NOT A JUDGEMENT ABOUT ANY SINGLE PRICE. Ninety-three per cent is a
    perfectly good number for a heavyweight champion and this function never says
    otherwise. It speaks only about the column: Usyk at 0.93 AND Kabayel at 0.87
    cannot both be true of one belt. Which of them is wrong is a question this
    predicate deliberately does not answer — see
    :func:`price_is_unlocated_in_broken_field` for the half that does, and note
    that it answers it from each leg's own book rather than by ranking them.

    :data:`MIN_FIELD_LEGS` IS IMPORTED, NOT RESTATED, AND IT IS LOAD-BEARING HERE
    FOR ITS OWN REASON. #5539 set the floor at three because a two-leg binary has
    no impossible arithmetic to appeal to; this rule needs it because on a two-leg
    field "both legs above 0.5" is ORDINARY OVERROUND — 0.55/0.52 sums to 1.07 and
    is a vig story. Production agreed before the floor went in: the only markets
    the gate caught that I could not defend were ``CONCACAF Nations League B`` and
    ``C``, two-leg fields summing 1.24 and 1.33.
    """
    priced = [float(p) for p in probabilities if p is not None]
    if len(priced) < MIN_FIELD_LEGS:
        return False
    return sum(1 for p in priced if p > SECOND_FAVOURITE_CEILING) >= 2


def price_is_unlocated_in_broken_field(
    source: Optional[str],
    resolution_source: Optional[str],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
) -> bool:
    """True when a leg's own book locates nothing and its field is not a distribution (#7059).

    WHAT A READER SAW. ``/hub/boxing`` named three different men near-certain to
    hold one belt — **Usyk 93% · Kabayel 87% · Itauma 79%**, with *Title is vacant*
    at 23% underneath — on the *WBC Heavyweight Title on January 1, 2027* card. The
    detail door agreed: sixteen priced legs summing to **299.5%** under a payload
    whose own ``mutually_exclusive`` flag reads true. Read from Kalshi directly
    (notice 26/27, ``event_ticker=KXWBCHEAVYWEIGHTTITLE-27``): ``volume_24h`` 0 and
    ``liquidity`` 0 on all seventeen legs, no bid at all on fourteen of them, and
    not one trade since **2026-07-13**. Itauma's book is ``bid 0.00 / ask 0.97`` —
    the venue's position is "worth somewhere between nothing and 97c, and nobody
    has touched it in 67 days". We printed 79%.

    THIS IS #6846'S MOVE, MADE AGAINST THE OTHER CONDITION. :func:`is_empty_book_midpoint`
    already refuses a price on a book this wide, but only when the price sits ON the
    book's midpoint, and condition 3 is not decoration — its docstring defends the
    exclusion explicitly: "a both-extremes book whose price is far from its midpoint
    got that price from a real trade (Kalshi falls back to ``last_price`` on a wide
    book), and those are honest lines". That defence is sound for a standalone leg
    and it is what spares these: ``current_probability`` EQUALS the newest snapshot's
    ``last_price`` on every one of the seventeen, to the cent. The trade is real. It
    is simply old, and a real trade on a book that is now empty is a PRINT, not a
    quote.

    Inside a proved single-winner field whose column has already been shown
    impossible, a print is not enough, and the reason is the one
    :func:`is_lone_ask_in_exclusive_field` gives for dropping ``ASK_ONLY_TRUSTED_MAX``:
    the frame changed, so the defence answers a question this caller is not asking.
    A field's numbers are read against each other and summed. When two of them
    cannot both be true (:func:`field_names_two_favourites`), the legs still entitled
    to a number are the ones whose own book pins one — and a book bounding nothing
    pins nothing, whatever it printed in July.

    THE RECENCY QUESTION IS NEVER ASKED, WHICH IS THE POINT. The obvious fix is a
    staleness predicate, and this module says not to pick one on a hunch (see
    :func:`price_is_unsupported`, which defers exactly that to #5314/#5781 — a
    pointer that has since gone dead: #5781 is CLOSED and Polymarket-specific, and
    #5314 is a p3 about three future-stamped rows). It is still not picked here.
    Nothing below reads a timestamp. Two independent reasons it must not:

      * OUR CAPTURE IS FRESH. ``snap_age_d`` is 0 on these legs — we re-record the
        same unchanging dead price faithfully every day — so anything keyed on
        ``captured_at`` passes them all.
      * THE VENUE'S OWN VOLUME IS THE SIGNAL AND WE DO NOT HAVE IT. ``futures_outcomes.volume``
        is populated on 3.2% of this class. The market-level column is worse than
        absent: ``futures_markets.volume_24h`` reads **373** on the specimen against
        the venue's 0, because ``volume_updated_at`` is a week old. A rule keyed on
        stored volume would have read this market as liquid. (Same trap on the F1
        card below, at 26,254.)

    MEASURED THROUGH THE ROUTE, NOT OFF THE STORED ROWS, AND THE TWO DISAGREE BY A
    FACTOR OF THIRTY-FIVE. Every number below is the served column: each candidate
    market's ``/api/futures/{id}`` payload fetched from production 2026-09-19, its
    published legs joined to their book columns by outcome id, **0 payload errors on
    135 + 35 fetches** (a rate-limited census understates without ever erroring — the
    first pass lost 103 of 135 and only the error count revealed it). A stored-row
    proxy is not available to this rule for a structural reason: 24 of the 35 markets
    whose STORED rows trip the gate already serve **no price at all**, having been
    withheld entirely by the four shipped arms. Counting them would have claimed 429
    legs and 28 emptied cards that no reader can see.

    THE SHIP, on the column a reader is actually shown: **12 legs across 2 markets,
    and NOT ONE market loses its last priced leg.**

      * *WBC Heavyweight Title on January 1, 2027* — 16 priced legs to 6, the served
        field from **2.995 to 1.14**. Usyk, Itauma, Joshua, Dubois and six more lose
        a number; Kabayel, *Title is vacant* and the four penny longshots keep theirs.
      * *WBC Lightweight Title on January 1, 2027* — 17 legs to 15, **1.66 to 0.69**,
        losing Lamont Roach at 96% and Bakhodur Usmanov.

    WHY BOTH HALVES ARE LOAD-BEARING, each measured the same way:

      * THE BOOK TEST ALONE takes **199 legs across 52 markets and empties 21 of
        them**, because it cannot tell a broken column from a sound one. Fifty of the
        markets it reaches serve a column the gate spares, and the damage is not
        marginal: *WBC Middleweight Title* (17 legs, served sum **exactly 1.00**),
        *Venice Film Festival: Coppa Volpi* (11 legs, **1.00**),
        *Spanish Grand Prix Qualifying (Q3): Pole Position* (22 legs, **1.00**) and
        *2027 Men's Rugby World Cup Winner* (3 legs, **1.00**) each lose EVERY price.
        A column that already sums to one is a distribution; a wide book inside it is
        corroborated by the arithmetic around it and needs no refusing.
      * THE FIELD TEST ALONE says the column is wrong, never which legs are. Acting on
        it whole-field would take the honest prices with the dead — the cost
        latency/578 accepted deliberately on #6996, and which this defect does not
        require, because here the bad legs announce themselves in their own books.

    THE GATE READS STORED PROBABILITIES AND THE PAGE SHOWS NORMALISED ONES, WHICH IS
    A REAL GAP AND IS EMPIRICALLY EMPTY TODAY. This arm runs inside
    ``_withheld_price_outcome_ids``, above ``normalize_display_probs`` (#1200), so it
    sees ``current_probability`` while a reader may see a squeezed value — and the
    squeeze bails out above ``_FIELD_SUM_MAX``, which is exactly why the specimen's
    93/87/79 reaches the page raw. Checked rather than assumed: over the 11 candidate
    markets that publish any price, the gate returns the SAME verdict on stored and on
    served values, **0 disagreements**. If a future field is squeezed below the bail-out
    while its stored column names two favourites, this rule would refuse a leg on a
    page that looks coherent; that market does not exist today and the check above is
    how the next session finds out it has started to.

    TWO MARKETS STILL NAME TWO FAVOURITES AFTERWARDS, and they are meant to. Their
    remaining legs are ones whose books DO bound them; refusing further would be
    chasing a sum, and this module withholds rather than rewrites (gotcha #21). An
    under-summing field is the honest residue of a refusal — renormalising would
    invent a price we are then graded on (``calibration_probability`` coalesces to
    stored values, gotcha #144 / ruling 103).

    NOTHING EMPTIES TODAY, BUT THE RULE PERMITS IT AND THAT IS DELIBERATE. Should a
    field's only priced legs all turn out to be prints on empty books, it goes blank
    and keeps its names — #6846 accepted the identical outcome ("a field whose only
    priced legs are all untaken offers has no price discovery to show"), and on a list
    surface an all-null card is DELETED rather than dashed (#7016), which is the cost
    that would then be paid.

    SCOPE AND FAIL-OPEN ARE :func:`needs_trade_evidence`'S, RESTATED IN NO NEW TERMS.
    Kalshi only (Polymarket's rule for these columns is a different one, gotcha #19),
    never a row carrying a verdict (settled means settled — withholding there deletes
    a result), and an absent bid or ask returns False so the leg is served exactly as
    it is today. Read-side only: nothing here mutates a stored price.
    """
    if (source or "").strip().lower() != KALSHI_BOOKMAKER:
        return False
    if row_carries_a_verdict(resolution_source):
        return False
    return book_bounds_nothing(yes_bid, yes_ask)


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

    AND A RETRACTED ROW IS AN UNGRADED ROW (#6876), which is the same sentence
    applied to a source that only looks like a grade. All 34,992 open Kalshi legs
    carrying ``ungradeable_result`` also carry ``is_winner = false``, so every one
    of them used to take the graded-LOSER branch below and be asked the ask arm
    alone. That branch is justified by "its number must be ~0" - true of a declared
    loss, false of a retraction, whose number is a live quote. So they now take the
    ungraded path and are asked both arms. Measured delta on production 2026-09-18:
    **10 legs on open markets** (the bid arm; the ask arm already fired on 157 of
    them and those verdicts do not move). The graded winner, the verdict-less graded
    row and the genuinely graded loser are all untouched -
    :func:`row_carries_a_verdict` affirms every source but the one.

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
    if row_carries_a_verdict(resolution_source):
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
    """True if this row is a fabricated midpoint a trade read can refute.

    The screen half of the trade arm, and the mirror of
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

    🔴 THE KALSHI ARM (#7222), AND THE PARAGRAPH BELOW IT PREDICTED THE TRIGGER.
    Until this ship the function returned False for anything that was not
    Polymarket, and the shape it screens for was live on Kalshi at scale. What a
    reader saw: ``/futures/55674185`` ("2027 CONCACAF Gold Cup Champion", tier 1)
    printed **eighteen of twenty-three teams at the same 18%**, ranked 4 through 21
    by nothing, over a single-winner column summing to **447%** with
    ``prices_withheld: 0``. Bermuda was 18% to win the Gold Cup; Costa Rica —
    three-time champion, beaten finalist in 2025 — sat at 2%, below Bermuda, Cuba
    and Guyana.

    THE MECHANISM IS THE WRITER'S TIGHT-BOOK RULE, AND THE TRADE WAS SITTING RIGHT
    THERE. ``_kalshi_yes_probability`` rule 1 takes the midpoint of any two-sided
    book narrower than ``_KALSHI_TIGHT_SPREAD_MAX`` (0.50), so a bid of 1c against
    an ask of 35c is "tight" and publishes 18% — while rule 2, the real trade, is
    never reached. Every one of those eighteen legs carries a newest Kalshi
    snapshot whose ``last_price`` is **0.01 or 0.02**. The two legs that came out
    right are not rescued by any rail: their bid is 0.00, rule 1 does not fire, and
    rule 2 reads their 2c trade. So the defect is not "one cent outside the
    empty-book rail" — it is the venue's own trade being outvoted by the midpoint
    of a spread nobody will trade inside, which is the exact sentence
    ``is_fabricated_midpoint`` was written for.

    WHY THE READ SIDE AND NOT THE WRITER. The poller SKIPS rather than nulls
    (``_kalshi_yes_probability`` rule 4 returns ``None`` and the caller moves on),
    so tightening rule 1 would stop the next fabrication and preserve all 1,004
    standing ones. That asymmetry is this module's founding observation (#6532:
    "the guard that stops a new fabrication is what preserves the old one"), and it
    is why the repair a reader can see is here.

    THE BID BOUND IS THE KALSHI-ONLY TERM, AND IT IS AN EXISTING CONSTANT. A
    two-sided Kalshi book with real money on both sides has a defensible midpoint
    even when the spread is wide, so the arm is scoped to books that state almost
    nothing on the bid: ``yes_bid <= EMPTY_BOOK_MAX_BID``, imported from
    ``feed_market_quality``, which is the sibling rail's already-shipped 0.05 and
    the tolerance the issue's own acceptance names. No new constant is introduced
    and none is restated. Measured on production 2026-09-19 over open Kalshi
    markets, legs whose served price is the exact midpoint of a >=0.20 spread and
    whose newest trade disagrees by at least ``_DISPLAY_ROUNDING``::

        bid bucket                         legs   markets   served   newest trade
        0.00 bid / 1.00 ask (the 0.5 seed)  339        42   0.5000       0.0720
        0.00 bid, real ask                   88        11   0.4411       0.0531
        0.00 < bid <= 0.05 (the Gold Cup)   577       355   0.1898       0.2394
        ------------------------------------------------ IN SCOPE: 1,004 legs
        bid > 0.05 (two-sided book)       2,129     1,007   0.5694       0.6082
                                                     ^ deliberately OUT of scope

    The 2,129 excluded legs are the judgement call this bound makes, and it is made
    in the withholding rule's fail-open direction: their books quote real money on
    both sides, their mean trade (0.61) sits ABOVE their mean served midpoint
    (0.57), and calling them fabricated would be an unmeasured claim about price
    discovery rather than a claim about an absent bid. They are not fixed here and
    are not asserted to be wrong.

    A REAL LONGSHOT THAT TRADES AT A CENT IS SPARED BY CONSTRUCTION, which is the
    issue's last acceptance bullet. ``is_fabricated_midpoint`` requires a spread of
    at least ``FEED_PHANTOM_MIN_SPREAD`` (0.20), so a 1c bid against a 3c ask — a
    genuine longshot with a tight book — never reaches this arm. It is the SPREAD,
    not the bid, that separates the two populations; the bid bound only keeps the
    arm off books that are genuinely two-sided.

    A RECORDED BOOK IS REQUIRED ON BOTH SIDES, and that is ``_is_ask_only_book``'s
    rule restated for the same reason it exists there: a ``None`` bid means the
    poller never recorded a book (the candle rails store none), not that the bid is
    zero, and this arm must not claim to know anything about those rows.
    ``is_fabricated_midpoint`` would coalesce them into a 0.0/1.0 book; requiring
    both columns keeps that coalescing inert on the Kalshi side.

    THE GRADE TEST IS PER-SOURCE, AND THE SIBLING PARAGRAPH BELOW IS WHY. This
    clause kept a bare ``is not None`` while its two siblings moved to
    :func:`row_carries_a_verdict` (#6876) because the retraction that helper carves
    out was written on KALSHI rows only — 34,993 open plus 3,854 resolved, and
    **zero** Polymarket legs on production 2026-09-18 — and the function returned
    False for anything that was not Polymarket. That reasoning is unchanged for
    Polymarket and it is exactly what makes the helper mandatory now that Kalshi is
    in scope: every one of the twenty-three Gold Cup legs carries
    ``resolution_source = 'ungradeable_result'``, so a bare ``is not None`` would
    disarm this arm on its own specimen — #6876's defect rebuilt one arm over.
    Polymarket keeps the narrower test rather than being widened onto a population
    that does not exist.
    """
    venue = (source or "").strip().lower()
    if venue not in MIDPOINT_TRADE_SOURCES:
        return False
    if venue == KALSHI_BOOKMAKER:
        if row_carries_a_verdict(resolution_source):
            return False
        if yes_bid is None or yes_ask is None:
            return False
        if float(yes_bid) > EMPTY_BOOK_MAX_BID:
            return False
    elif resolution_source is not None:
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

    🔴 A ZERO ``last_price`` IS EVIDENCE ON POLYMARKET AND IS *NOT* EVIDENCE ON
    KALSHI, AND INVERTING THAT WOULD BE THE WORST BUG THIS ARM COULD HAVE (#7222).
    The paragraph above earns Polymarket's reading from its writer: ``polymarket.py``
    assigns ``last_trade_price`` straight through, so a stored 0.0 means the venue
    said zero. Kalshi's writers say the opposite with the same number — an untraded
    Kalshi leg is quoted ``last_price 0``, which is why
    ``_kalshi_yes_probability`` rule 2 requires ``last_price > 0`` before it will
    read a trade at all and why ``kalshi_empty_book._is_ask_only_book`` reads a zero
    there as "no trade" when identifying a book nobody has touched. Taking a Kalshi
    zero as evidence would therefore refute every untraded Kalshi midpoint against a
    trade that never happened — it would blank the honest longshots and cite a
    fabrication while doing it. So the Kalshi side requires a strictly positive
    trade, which is the same bar its own writer sets one module over, and the
    Polymarket side is untouched.
    """
    if not needs_trade_disconfirmation(
        source, resolution_source, probability, yes_bid, yes_ask
    ):
        return False
    if not has_trade_evidence or last_price is None or probability is None:
        return False
    if (source or "").strip().lower() == KALSHI_BOOKMAKER and float(last_price) <= 0:
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
    in_exclusive_field: bool = False,
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
        in_exclusive_field=in_exclusive_field,
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
