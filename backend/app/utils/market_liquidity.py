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
     figure.  A **presence** test — ``> 0`` — and deliberately not a dollar
     floor.  Q428 measured the 24h-volume distribution across the 328 live
     ladder markets and found it running continuously from $0 to $1,900 with no
     empty band to put a threshold in; any floor would be a knob wearing a
     principle.  Presence is not a knob.

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
    unknown      — neither fact was checkable (no book AND no volume figure).

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
#: ⚠️ MEASURED 2026-08-28, AND IT DOES NOT FIRE ON POLYMARKET YET. Across all
#: 336 US Open ladder markets, Gamma serves ``volume24hr`` as **positive on 66
#: and ABSENT on 270** — never as an explicit ``0``. Absent is uncheckable here,
#: not zero, so on the surface this signal was built for the second level is
#: currently unreachable and every mark is a ``thin``.
#:
#: That is gotcha #53 being obeyed rather than a bug: Gamma returns the same
#: shape for "nobody traded this" and "we do not compute this field", and a
#: mark that could not tell them apart would be inventing the half we do not
#: have. Q428 reads the same absence in the opposite direction — it DECLINES a
#: last-trade escape hatch when ``volume24hr`` is not positive — and that is
#: sound, because failing closed on an ambiguous signal costs nothing while
#: *asserting* on one costs the reader's trust.
#:
#: THE DISAMBIGUATION IS AVAILABLE AND IS NOT TAKEN HERE: Gamma also serves
#: lifetime ``volume``, and a market with lifetime volume but no 24h figure is
#: strong evidence of genuinely zero recent trading. That is a third ingredient
#: and a change to the rule, so it needs its own measurement rather than a
#: last-minute inference. Banked for the next queue; see the UX-P157 report.
REASON_NO_TRADES_24H = "no_trades_24h"
#: The gap between the best bid and the best ask is at least as large as the
#: number being quoted.
REASON_SPREAD_EXCEEDS_PRICE = "spread_exceeds_price"

#: Said ONCE per surface, never per cell. The limit is part of the definition:
#: a number with no mark on it has not been cleared, it has been left alone.
LIQUIDITY_DEFINITION = (
    "We mark a number when the market behind it is barely being traded — nobody "
    "has traded it in the last day, or the gap between what buyers offer and what "
    "sellers want is wider than the number itself. A half mark means one of those "
    "is true; a hollow mark means both are. Where a venue publishes nothing to "
    "check against we cannot mark, so a number with no mark is one we have not "
    "been able to question."
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
) -> dict[str, Any]:
    """One outcome's book → ``{"level": str, "reasons": list[str]}``.

    Every argument is keyword-only and optional, because the three of them
    arrive from three different columns on two different tables and a
    positional call site would be a silent bid/ask transposition waiting to
    happen.

    Never raises.  A poison value (a string, a NaN, a dict) is an
    *uncheckable* fact, not a failing one — a mark invented from a parse error
    would be indistinguishable on the page from a mark we measured.
    """
    reasons: list[str] = []
    checked = 0

    volume = _as_float(volume_24h)
    if volume is not None:
        checked += 1
        if volume <= 0:
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
