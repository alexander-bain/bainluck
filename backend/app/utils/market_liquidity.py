"""How thin the market behind a number is — one rule, every surface.

═══ WHY THIS EXISTS (Alex, 2026-08-28) ═══

His words, as ruled: *"a really clean, universal signal for illiquidity"*, with
three constraints — the symbol **grades** (at least two levels), the reveal says
**precisely when the probability was last updated**, and the same symbol works
on grids, cards and props **everywhere**.  Issue #2256 carries his own framing:
*"Indicate on the site when probabilities are illiquid and less meaningful."*

The thing it is for is visible on the US Open bracket grid today.  Q428 took the
grid from 27 monotonicity violations to 16 by fixing three of our own bugs, and
then stopped, because the residual 16 are **faithfully what the markets say** —
Venus Williams quoted 0.8% to reach the quarter-final and 3.6% to reach the
semi-final, on two books that between them traded nothing at all in 24 hours.
The charter forbids smoothing and Alex's triage ruling forbids deleting them, so
the only honest move left is the one he ruled: **say out loud that the number is
thin**, and let the reader discount it themselves.  #2257 is the open question
this answers.

═══ WHAT WE ACTUALLY KNOW, AND THEREFORE WHAT THE GRADE MAY BE BUILT FROM ═══

Two facts per outcome, and no others.  Both arrived on this surface with Q428,
which taught ``tournament_price_refresh`` to write the book alongside the price
it produced — before that, 181 of 328 US Open ladder rows held a probability
sitting outside their own stored ``[bid, ask]`` and its commit says in as many
words that Alex's ask was *"unbuildable for want of the column"*.

  1. **Did anybody trade it.**  ``FuturesMarket.volume_24h``, the venue's own
     figure, read together with ``volume_updated_at`` — *when we asked*.  A
     **presence** test — ``> 0`` — and deliberately not a dollar floor.  Q428
     measured the 24h-volume distribution across the 328 live ladder markets
     and found it running continuously from $0 to $1,900 with no empty band to
     put a threshold in; any floor would be a knob wearing a principle.
     Presence is not a knob.

     **UX-P158 measured what an ABSENT figure means, and it means zero.**  See
     the note on ``REASON_NO_TRADES_24H``: Gamma omits the field rather than
     serving ``0``, and the Polymarket trade tape separates the three cohorts
     with no exceptions at all.  So an absence, *observed recently enough to be
     about the last day*, is now a failing fact rather than an unreadable one.
     That second clause is the whole of the change and it is why this fact
     takes a timestamp: an observation is only evidence about the window it
     describes while it is younger than that window.

  2. **Is the book wider than the number it quotes.**  ``ask - bid >= midpoint``
     — a comparison of two measured quantities with **no constant in it at
     all**.  This is the shape #2257 describes: a book quoted ``0.00 / 0.08`` is
     eight cents wide and therefore *tight* by ``FEED_PHANTOM_MIN_SPREAD``
     (0.20, absolute, measured on the feed's mid-range distribution), while its
     uncertainty band is twice the number it is printing.  Every one of the 16
     residual violations lives in exactly that gap.

═══ THE ONE OBJECTION THAT HAS TO BE ANSWERED HERE ═══

Q428 measured this same relative-width test and **refused to ship it**, and the
refusal was right: the relative-spread distribution over those 328 markets has
no empty middle (77 of them straddle the boundary), so as a *filter* it would
have been a tuned knob, and it would have cut the grid from 416 priced cells to
about 120.

It is used here anyway, and the reason is that **a filter's error and a mark's
error are not the same kind of error**.  A filter that misjudges a straddling
market deletes the cell: the reader never learns a number existed, and cannot
tell a suppressed cell from an unquoted one.  A mark that misjudges the same
market puts a caution beside a number that is still printed, still readable, and
still checkable — the reader sees both the number and our doubt about it.  That
is ruling 048's own logic in a different costume (*a duplicate is visible and
reversible, a wrong absorption is neither*), and it is why the presentation
route is open to a test the filtering route is not.

Stated plainly so a later queue does not "tidy" this into a filter: **this rule
may never decide whether a cell renders.**  It decides what is drawn beside it.

═══ THE GRADE ═══

Level is the **count of those two facts that we checked and that failed**.  Two
binary facts give exactly the two levels Alex asked for, and the count needs no
constant of its own:

    traded  (0)  — checked, and nothing is wrong.  Draws nothing.
    thin    (1)  — one of the two failed.
    barely  (2)  — both failed.  The near-dead book.
    unknown      — neither fact was checkable (no book AND no volume
                   observation recent enough to speak about the last day).

``unknown`` draws nothing, and that is a deliberate, stated limit rather than a
verdict: we can only mark a number where the venue publishes a book, and an
absent mark is therefore not a claim that the market is healthy.  The surfaces
say so once, in ``LIQUIDITY_DEFINITION`` — the same discipline as
``tournament_props.FRESHNESS_DEFINITION``, which exists because a label that
over-claims is worse than no label.

A partially-checkable outcome grades on what it has: one known failing fact is
``thin`` even when the other could not be checked.  ``thin`` is the honest
floor there — we have found one thing wrong and cannot rule out a second.

═══ WHAT THIS IS NOT ═══

Not ``confidence_tier`` (``utils/feed_market_quality.py``, the feed's 1–3 signal
bars).  That is a *blended* score over sources, movement, volume and agreement,
computed for a feed card, and volume is one weighted input to it.  This is a
single un-blended fact about one outcome's own book, which is why it can be
graded honestly at a grid cell where a blended score could not.

Imports nothing from the app.  Pure arithmetic over three optional numbers, so
it can be called from a task, a route, a builder or a test with no session.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "LIQUIDITY_BARELY",
    "LIQUIDITY_DEFINITION",
    "LIQUIDITY_LEVELS",
    "LIQUIDITY_THIN",
    "LIQUIDITY_TRADED",
    "LIQUIDITY_UNKNOWN",
    "REASON_NO_TRADES_24H",
    "REASON_SPREAD_EXCEEDS_PRICE",
    "VOLUME_OBSERVATION_MAX_AGE_HOURS",
    "grade_liquidity",
    "thinnest_liquidity",
]

#: Checked, and neither fact is wrong. No mark.
LIQUIDITY_TRADED = "traded"
#: One of the two facts failed.
LIQUIDITY_THIN = "thin"
#: Both failed.
LIQUIDITY_BARELY = "barely"
#: Neither fact was checkable. No mark, and not a verdict — see the module note.
LIQUIDITY_UNKNOWN = "unknown"

#: Thinnest last. ``thinnest_liquidity`` orders by index into this list, so the
#: order IS the severity contract — the boards' "as fresh as its oldest leg"
#: rule (UX-P135), applied to liquidity.
LIQUIDITY_LEVELS = (
    LIQUIDITY_TRADED,
    LIQUIDITY_UNKNOWN,
    LIQUIDITY_THIN,
    LIQUIDITY_BARELY,
)

#: The venue reported no trades at all in the last 24 hours.
#:
#: ⚠️ AN ABSENT ``volume24hr`` IS A ZERO, AND THAT IS MEASURED, NOT ASSUMED.
#: UX-P157 shipped this reason unable to fire on Polymarket: Gamma served
#: ``volume24hr`` positive on 66 of 336 US Open ladder markets and ABSENT on
#: 270, never as an explicit ``0``, so the fact was uncheckable on the very
#: surface the ruling was about and every real mark could only be a ``thin``.
#: It banked the suspected disambiguation rather than inferring it.
#:
#: UX-P158 went and measured it, and the answer was cleaner than the suspicion.
#: Every one of the 328 markets Gamma still served was cross-checked against
#: the Polymarket **trade tape** (``data-api.polymarket.com/trades``), which is
#: an independent instrument — trades, not a computed aggregate:
#:
#:     ``volume24hr`` present (always > 0)   64 markets — 64/64 traded in 24h
#:     absent, lifetime ``volume`` present  133 markets —  0/133 traded in 24h,
#:                                                       133/133 traded at some
#:                                                       point
#:     both absent                          131 markets — 131/131 have NEVER
#:                                                       traded, not once
#:
#: Three cohorts, zero exceptions, 328/328. Gamma **omits a zero-valued volume
#: field rather than serialising it**, and the same signature shows on its
#: other numerics on this population (no explicit ``0`` ever appears for
#: ``bestBid`` or ``oneDayPriceChange`` either — they are simply absent).
#:
#: This is gotcha #53 discharged the way the gotcha itself prescribes, not
#: waived. The gotcha does not say "never read an absence"; it says an absence
#: and a zero share a response shape, so **disambiguate with a second signal**
#: before writing a claim. The trade tape is that second signal, and it is a
#: different endpoint measuring a different thing.
#:
#: WHAT THE INFERENCE STILL NEEDS, AND WHY THIS FACT NOW TAKES A TIMESTAMP.
#: "The venue reported no 24h volume" is only a statement about *the last day*
#: while the observation is younger than a day. Measured on the same surface on
#: 2026-08-29: 115 of the 336 ladder rows carried a price — and therefore a book
#: and a volume figure — last written on 2026-08-25, 83 hours earlier. Reading a
#: NULL on one of those as "nobody traded it today" would be exactly the
#: invention this module refuses, so the fact is checkable only against a
#: current observation.
#:
#: Those 115 are not a register gap; all 336 are pinned. The rail's own summary
#: accounts for them exactly — 8 Gamma no longer serves, and 107 are Q428's
#: decline, a book it will not publish a price from. Which means the STALEST
#: books on the surface belonged to the markets this mark most needs to
#: describe, and it is why ``tournament_price_refresh`` now records the volume
#: observation for every market Gamma RETURNS rather than every market it
#: prices.
#:
#: NOT USED, DELIBERATELY: lifetime ``volume`` separates "traded once, not
#: today" (133) from "never traded at all" (131), and that is a real third
#: state. It is not a third LEVEL — Alex asked for a graded symbol, the grade
#: is the count of two failing facts, and a third level would be a different
#: ruling rather than this one implemented. Banked in the fixture for whoever
#: needs it.
REASON_NO_TRADES_24H = "no_trades_24h"
#: The gap between the best bid and the best ask is at least as large as the
#: number being quoted.
REASON_SPREAD_EXCEEDS_PRICE = "spread_exceeds_price"

#: How old a volume observation may be and still be evidence about "the last
#: day".
#:
#: NOT A TUNED THRESHOLD, and the distinction matters because this module's
#: whole claim is that it has no knobs in it. ``volume24hr`` measures a
#: 24-hour window; an observation of it taken ``h`` hours ago describes the
#: window ``[now-24-h, now-h]``, which stops overlapping *today* at all once
#: ``h`` passes 24. The number is the field's own definition, and it is the
#: LOOSEST bound that keeps the sentence true rather than a value picked off a
#: distribution. Moving it would not re-tune the mark; it would make the mark
#: say something the venue did not.
VOLUME_OBSERVATION_MAX_AGE_HOURS = 24.0

#: Said ONCE per surface, never per cell. The limit is part of the definition:
#: a number with no mark on it has not been cleared, it has been left alone.
#:
#: ⚠️ THE TWO FACTS ABOVE ARE NOT IN IT, AND THAT IS A RULING (Alex, 2026-08-29,
#: looking at the shipped page): *"no need to reference buyers and sellers. can
#: just clarify that the numbers isn't moving and is less reliable."*  The grade
#: is still the count of two failing facts — that is this module's job and it is
#: unchanged — but the arithmetic that produced the count is ours to carry, not
#: the reader's to parse.  "One sign of that" and "both" is the whole of what a
#: reader needs to order two symbols.  Mirrored word for word in
#: ``frontend/lib/liquidity.LIQUIDITY_DEFINITION`` and
#: ``LiquidityMarkView.Liquidity.definition``.
LIQUIDITY_DEFINITION = (
    "We mark a number when the market behind it is barely being traded, which "
    "usually means it hasn't moved in a while and is less reliable. A half mark "
    "means we found one sign of that; a hollow mark means we found both. Where a "
    "venue publishes nothing to check against we cannot mark, so a number with no "
    "mark is one we have not been able to question."
)


def _as_float(value: Any) -> Optional[float]:
    """Any → float, or ``None``. NaN is ``None``: it is not a measurement."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def grade_liquidity(
    *,
    bid: Any = None,
    ask: Any = None,
    volume_24h: Any = None,
    volume_observed_age_hours: Any = None,
) -> dict[str, Any]:
    """One outcome's book → ``{"level": str, "reasons": list[str]}``.

    Every argument is keyword-only and optional, because they arrive from four
    different columns on two different tables and a positional call site would
    be a silent bid/ask transposition waiting to happen.

    ``volume_observed_age_hours`` is how long ago the venue was asked for this
    market's volume — ``FuturesMarket.volume_updated_at`` differenced against
    now by the caller, which owns the clock so this module does not have to.
    It gates the volume fact in BOTH directions, and the symmetry is the point:
    a figure read four days ago is no more a statement about today when it is
    positive than when it is absent.  A negative age is a disagreement between
    two clocks rather than a measurement, so it is refused, not clamped.

    Never raises.  A poison value (a string, a NaN, a dict) is an
    *uncheckable* fact, not a failing one — a mark invented from a parse error
    would be indistinguishable on the page from a mark we measured.
    """
    reasons: list[str] = []
    checked = 0

    volume = _as_float(volume_24h)
    age = _as_float(volume_observed_age_hours)
    observation_is_current = (
        age is not None and 0.0 <= age <= VOLUME_OBSERVATION_MAX_AGE_HOURS
    )
    if observation_is_current:
        checked += 1
        # `volume is None` is the measured absence, not a missing read: we know
        # the venue was asked, we know when, and we know from 328/328 against
        # the trade tape that it omits the field instead of serving a zero.
        if volume is None or volume <= 0:
            reasons.append(REASON_NO_TRADES_24H)

    best_bid = _as_float(bid)
    best_ask = _as_float(ask)
    if best_bid is not None and best_ask is not None and best_ask >= best_bid:
        # `ask >= bid` guards a crossed/garbled book: a negative spread is not a
        # tight market, it is a reading we should not grade from at all.
        checked += 1
        midpoint = (best_bid + best_ask) / 2.0
        # `>=` and not `>`: a 0.00/0.00 book is no offers in either direction,
        # which is the extreme case this signal exists for, and it is the one
        # value where the two sides of a `>` would let it through unmarked.
        if (best_ask - best_bid) >= midpoint:
            reasons.append(REASON_SPREAD_EXCEEDS_PRICE)

    if checked == 0:
        return {"level": LIQUIDITY_UNKNOWN, "reasons": []}
    if not reasons:
        return {"level": LIQUIDITY_TRADED, "reasons": []}
    return {
        "level": LIQUIDITY_THIN if len(reasons) == 1 else LIQUIDITY_BARELY,
        "reasons": reasons,
    }


def thinnest_liquidity(levels: list[Optional[str]]) -> str:
    """The worst grade among several contributors — a blend's own grade.

    A grid cell is one number built from two venues, and it is only as solid as
    the thinner of the two books inside it.  Same shape as
    ``tournament_board.governing_age_hours``, which makes a row as fresh as its
    OLDEST leg for exactly the same reason: the reader sees one number, so the
    number has to answer for everything that went into it.

    An empty list, or one holding only unrecognised values, is
    ``LIQUIDITY_UNKNOWN`` — nothing to say rather than a cleared verdict.
    """
    worst = -1
    for level in levels:
        if level not in LIQUIDITY_LEVELS:
            continue
        worst = max(worst, LIQUIDITY_LEVELS.index(level))
    if worst < 0:
        return LIQUIDITY_UNKNOWN
    return LIQUIDITY_LEVELS[worst]
