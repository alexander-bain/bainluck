"""The pre-match reading a settled card prints, and WHICH VENUE said it.

── WHY A SETTLED CARD NEEDS THIS AT ALL (ux/1036 Tier A) ────────────────────────

Alex, on /sports "Just Happened" at phone width, 2026-09-02: *"How come none of
these show pre-event probability?"* He was reading a column of FINAL cards where
every pre-match number had been collapsed into one grey footnote — ``Opened
40/60`` — which does not say which team is the 40. A live card on the same page
gives each team its own number.

That footnote is also the wrong SHAPE for the question. Two figures in fixed
positions with a slash between them is a duel a reader has to decode against the
name order printed elsewhere on the card; UX-P166 already had to fix it summing
to 101. A number belongs beside the name it is about.

── THE LADDER, AND WHY IT IS ORDERED RATHER THAN MERGED ─────────────────────────

Alex's rule, given for the tennis hub on the same day (#2747) and reused here
verbatim: **Kalshi → Polymarket → sportsbook blend, labelled by source, never
blank when any pre-match reading exists.**

Ordered, not blended. A blend of "what Kalshi thought" and "what the books
thought" is a number no venue ever quoted, and the whole point of a settled card
is to show a reader the forecast that was actually on offer before the match. The
blend is the product for a LIVE question (standing ruling: one number per
question); a settled pre-match reading is history, and history has an author.

Prediction markets come first because they are the product's subject. Sportsbooks
are the fallback, and a fallback that is a different KIND of claim has to say so
— hence :func:`needs_source_label`. "The market opened them at 40%" and "the
books opened them at 40%" are not the same sentence, and printing the second as
the first is the class of defect ux/1034 A3 removed from the hub's footnote.

── WHAT COUNTS AS A PRE-MATCH READING ───────────────────────────────────────────

For the two prediction-market rungs, the last ``win_prob_snapshots`` row captured
at or before ``commence_time``. Not ``futures_outcomes.opening_probability``:
measured on production 2026-09-02, that column is "the first price we happened to
see", and on the linked game markets sampled it was captured AFTER the first ball
— e.g. event 15301117 (Hull City v Aston Villa, 14:34Z) carries an opening
captured at 16:15Z. A number stamped after kickoff is not a prior, and it looks
exactly like one.

For the books rung, ``Event.opening_*``, which ``_maybe_set_opening_odds`` keeps
refreshing until the game starts and then freezes — a genuine last-pregame
consensus by construction.

── AWAY IS ACCEPTED, NOT ASSUMED ────────────────────────────────────────────────

Both writers store the pair, and both store complements. The served away side is
therefore used when it IS a complement of the home side and derived otherwise —
rather than derived unconditionally, which would silently discard a real reading
whenever a source stopped agreeing with itself, and rather than trusted
unconditionally, which is how a card prints two numbers that do not answer one
question. The rounding of the pair is not decided here; it is
``rendered_duel_percents``' job at serialization, once, for the same reason
UX-P114 gave.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

# The two prediction-market rungs, in Alex's order. Source ids as the payload and
# `win_prob_snapshots.source` spell them — never a display name; those are the
# renderer's business and ruling 141 keeps venue names out of narrative copy.
PREDICTION_MARKET_SOURCES: tuple[str, ...] = ("kalshi", "polymarket")

# The sportsbook consensus rung. Deliberately generic: `Event.opening_*` is a
# MEDIAN across whichever books were still quoting (#1841), so there is no one
# venue to name and naming one would be false.
BOOKS_SOURCE = "books"

PREMATCH_LADDER: tuple[str, ...] = PREDICTION_MARKET_SOURCES + (BOOKS_SOURCE,)

# How far a served pair may miss 1.0 and still be treated as the two sides of one
# question. Wide enough for the 4-dp rounding both writers store, tight enough
# that two unrelated numbers never pass.
_COMPLEMENT_TOLERANCE = 0.01


def _as_probability(value: Any) -> Optional[float]:
    """A usable probability, or ``None``.

    Rejects the endpoints as well as the out-of-range: a pre-match reading of
    exactly 0 or 1 is a settled price that leaked backwards past the clock
    filter, and it would render as "the market called it impossible" — the
    strongest claim on the card, made by an artefact.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if not 0.0 < number < 1.0:
        return None
    return number


def _pair(home: Any, away: Any) -> Optional[tuple[float, float]]:
    """``(home, away)`` as a coherent pair, anchored on home."""
    home_prob = _as_probability(home)
    if home_prob is None:
        return None
    away_prob = _as_probability(away)
    if away_prob is None or abs(home_prob + away_prob - 1.0) > _COMPLEMENT_TOLERANCE:
        away_prob = round(1.0 - home_prob, 6)
    return home_prob, away_prob


def prematch_source_rank(source: Any) -> int:
    """Where this source sits on the ladder — lower wins.

    Exported so a surface that has to CHOOSE between two readings it already
    holds (the tennis hub picks between the venues pinned on one matchup) sorts
    by the same order the feed resolves by, rather than growing a second copy of
    Alex's ordering that can drift out of step with this one. An unknown source
    sorts last: it is still usable, it is simply never preferred over a rung we
    have a reason to trust.
    """
    try:
        return PREMATCH_LADDER.index(source)
    except ValueError:
        return len(PREMATCH_LADDER)


def is_prediction_market_source(source: Any) -> bool:
    """Is this rung a prediction market — i.e. does the number need no caveat?"""
    return source in PREDICTION_MARKET_SOURCES


def needs_source_label(source: Any) -> bool:
    """Must the card say where this number came from?

    Alex: *"labelled when not a prediction market."* A prediction-market opening
    is the thing this product is about and reads as itself; anything else is a
    different claim wearing the same shape, so it carries its source.
    """
    return source is not None and not is_prediction_market_source(source)


def resolve_prematch_reading(
    *,
    by_source: Optional[Mapping[str, Any]] = None,
    books_home: Any = None,
    books_away: Any = None,
    ladder: Iterable[str] = PREMATCH_LADDER,
) -> Optional[dict]:
    """The first rung of the ladder that has a coherent pre-match pair.

    ``by_source`` maps a prediction-market source id to ``(home, away)`` — the
    last snapshot at or before ``commence_time`` for that source. The books rung
    is passed separately because it lives on the event row rather than in the
    snapshot table.

    Returns ``{"home_probability", "away_probability", "source"}``, or ``None``
    when no rung has a reading. ``None`` means "we hold nothing", which is the
    only case where a settled card is allowed to print no pre-match number.
    """
    readings = dict(by_source or {})
    for source in ladder:
        if source == BOOKS_SOURCE:
            pair = _pair(books_home, books_away)
        else:
            served = readings.get(source)
            if served is None:
                continue
            if isinstance(served, Mapping):
                pair = _pair(served.get("home"), served.get("away"))
            else:
                home, away = (list(served) + [None, None])[:2]
                pair = _pair(home, away)
        if pair is None:
            continue
        return {
            "home_probability": pair[0],
            "away_probability": pair[1],
            "source": source,
        }
    return None
