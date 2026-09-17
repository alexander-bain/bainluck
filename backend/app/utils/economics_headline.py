"""Pick the market that answers the ``/economics`` recession headline.

═══ WHY THIS EXISTS (UX-P273 / #2674) ═══

The recession card printed a **hardcoded** question — "Recession by end of
2026" — above a number chosen by whichever binary recession market the theme
loop happened to process last. Nothing bound the two together, so the card
asked one question and answered another. Measured on production 2026-09-02:
the card read **13%**, which is market ``109350`` *"Will the IMF declare a
global recession before 2027?"* at 12.5% — a global IMF declaration, printed
under a US-2026 label — while the market the label actually asks about
(``113012`` *"US recession by end of 2026?"*) read 12.0% and was not on the
card at all.

Two things made it undefined rather than merely wrong:

* the query that feeds the theme loop (``economics.py``) carries **no
  ``ORDER BY``**, so "the last one processed" is not a stable order — the
  headline could change country or year on any reingest, and
* ``side_markets`` is ``rec_side[:6]`` while the headline was the **last**
  match, so the headline was structurally almost never among the rows printed
  beneath it and a reader could not check it.

The repair has two halves and only the first is load-bearing:

1. **The binding.** The route publishes the selected market's own question
   alongside its probability, and the page renders that question. The label
   and the number now come from one market, so they cannot disagree — *by
   construction*, whatever this ranking does. Every other question on the card
   already worked this way: all nine ``MarketRow`` call sites render ``q``
   from the payload, and the gas card renders ``g.label``. The headline was
   the only question-shaped label on the page that was a literal.

2. **The ranking below.** This only decides *which* honest question gets the
   headline. A bad ranking makes the card less interesting; it can no longer
   make it lie.

═══ THE RANKING ═══

Candidates are sorted by ``(scope_rank, year_rank, market_id)``:

* ``scope_rank`` — 0 for a market with no non-US scope marker, 1 otherwise.
  ``/economics`` is a US macro page, so "Japan recession in 2026?" is a real
  market but the wrong answer to the card's question.
* ``year_rank`` — 0 names the current year (or "before <next year>", which is
  the same window and is how Kalshi usually phrases it), 1 names no year at
  all ("Recession this year?"), 2 names some other year.
* ``market_id`` — a total tiebreak, so the result never depends on query
  order. This is the property the old code lacked.

⚠️ Scope markers are matched on **word boundaries**. A substring test cannot
be used here: ``"us" in "Will the IMF..."`` is true via "declare", and more to
the point ``"uk"`` is a substring of nothing useful while ``"us"`` is a
substring of "August" and "because". The regex below is anchored with ``\b``
and the guard suite pins the two worked examples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "RecessionCandidate",
    "select_recession_headline",
    "LadderCandidate",
    "select_mortgage_ladder",
]


@dataclass(frozen=True)
class RecessionCandidate:
    """One binary recession market the headline may be drawn from."""

    market_id: int
    name: str
    prob_pct: float


# Tokens that put a market outside this page's US-macro question. "global" and
# "imf" are not countries, but a global IMF declaration is just as wrong an
# answer to "will the US enter a recession" as Japan's is — and the IMF market
# is the one that was actually on screen when #2674 was filed.
_NON_US_SCOPE = re.compile(
    r"\b(?:"
    r"canada|canadian|japan|japanese|uk|u\.k\.|united\s+kingdom|britain|british"
    r"|china|chinese|germany|german|france|french|eurozone|euro\s+area"
    r"|europe|european|india|indian|australia|australian|mexico|mexican"
    r"|brazil|brazilian|russia|russian|korea|korean"
    r"|global|globally|worldwide|imf"
    r")\b",
    re.IGNORECASE,
)

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_BEFORE_YEAR = re.compile(r"\bbefore\s+((?:19|20)\d{2})\b", re.IGNORECASE)


def _scope_rank(name: str) -> int:
    """0 when the market is US-scoped, 1 when it names somewhere else."""
    return 1 if _NON_US_SCOPE.search(name or "") else 0


def _year_rank(name: str, current_year: int) -> int:
    """0 = names the current year, 1 = names no year, 2 = names another year."""
    text = name or ""
    years = {int(y) for y in _YEAR.findall(text)}
    if not years:
        return 1
    if current_year in years:
        return 0
    # "before 2027" closes at the end of 2026 — the same window as "by end of
    # 2026", and the phrasing Kalshi reaches for most often.
    for match in _BEFORE_YEAR.finditer(text):
        if int(match.group(1)) == current_year + 1:
            return 0
    return 2


def select_recession_headline(
    candidates: Sequence[RecessionCandidate],
    *,
    current_year: int,
) -> RecessionCandidate | None:
    """Return the market that should headline the recession card, or None.

    ``current_year`` is **required and has no default** on purpose. A default
    of ``datetime.now().year`` would make every test in the guard suite branch
    on the wall clock (gotcha #44), and would let a future call site silently
    acquire a clock dependency the author never chose.

    Returns ``None`` for an empty candidate list; the route then publishes a
    null question and the page renders no headline at all, rather than showing
    a number with no question or a question with no number.
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            _scope_rank(c.name),
            _year_rank(c.name, current_year),
            c.market_id,
        ),
    )


# ═══ THE MORTGAGE CARD (#6702) ═══
#
# The same defect as #2674, one section further down the page and with a
# distribution instead of a single number. The housing card was headed by the
# hardcoded string "30-year mortgage rate by end of 2026" above whichever
# mortgage market with three-or-more outcomes the theme loop saw LAST — on the
# same ORDER BY-less query — and on production 2026-09-16 that was market
# ``60775281`` *"30-year mortgage rate this week"*, a market resolving the next
# morning, drawn under an end-of-year headline.
#
# The repair has the same two halves, in the same order of importance: the card
# ships the selected market's own question (it can no longer ask one thing and
# answer another, whatever this ranking does), and the ranking below decides
# only which honest question gets the card.
#
# ═══ WHY THE RANK IS A SPREAD ═══
#
# Two mortgage ladders were open when this was written and they are not equally
# worth a card:
#
#   109321   "How high will 30yr mortgage rate get this year?"   99.9 → 57.0
#   60775281 "30-year mortgage rate this week"                   94.5 → 68.0
#
# The second is thirteen rungs between 6.73% and 6.85%: monotone, honest, and
# almost information-free — a reader learns nothing from a bar chart whose bars
# are all nearly the same height. The first sweeps from a near-certainty down
# through a coin flip, which is the shape that makes a ladder worth drawing. The
# property that separates them is the SPREAD of the prices, so that is what is
# ranked.
#
# Measured on the probabilities, never on a threshold parsed out of a label —
# the same discipline as ``economics._ladder_rung``, and for the same reason:
# these ladders are phrased "Above 6.73%", "At least 370" and "Before Jan 1,
# 2028" in one pool, and only the price is comparable across all three.
#
# ⚠️ AND THE RANKING HAS NOT YET HAD TO BREAK A TIE IN PRODUCTION. Of the three
# mortgage markets with rungs open on 2026-09-16, TWO never reach this helper:
# ``should_exclude_from_featured`` drops a market whose leader clears 0.98, and
# a cumulative ladder's leader is its LOOSEST bound, which is a near-certainty
# by construction. 109321 leads at 99.9 and 115646 at 100.0, so both are gone
# before the theme loop, and the card is drawn from the single survivor. That
# interaction is filed separately — it is a shared predicate on three routes and
# is not this card's to change. The rank below is written for the pool, not for
# tonight; what tonight's pool needs is the BINDING and the raw rows.
#
# ⚠️ CANDIDACY IS THE LOAD-BEARING HALF OF THIS HELPER, NOT THE RANKING. Only a
# market the caller has already confirmed is a cumulative ladder may be offered
# here. The third market, Polymarket's ``115646``, carries outcomes ``↑ 6.20%``,
# ``↓ 6.00%`` and a stray ``Yes``/``No`` pair; it is not a ladder,
# ``economics._is_cumulative_ladder`` correctly refuses it, and a card drawn
# from it would be rescaled into a fake distribution — which is the defect this
# issue is about. Its price spread is the widest of the three (100 → 0), so
# ranking WITHOUT the candidacy gate would pick exactly the wrong market.


@dataclass(frozen=True)
class LadderCandidate:
    """One cumulative-threshold market a distribution card may be drawn from.

    ``probs`` are percentages (0–100), in any order — the spread does not care.
    The caller has already established that this market IS a ladder; see the
    warning above.
    """

    market_id: int
    name: str
    probs: Sequence[float]


def _spread(probs: Sequence[float]) -> float:
    """How far a ladder's prices travel, in percentage points.

    Rounded to one decimal — the same precision the page prints — so that a
    float hair's breadth between two ladders cannot flip the card from one
    reingest to the next. Ties fall through to ``market_id``.
    """
    if not probs:
        return 0.0
    return round(max(probs) - min(probs), 1)


def select_mortgage_ladder(
    candidates: Sequence[LadderCandidate],
) -> LadderCandidate | None:
    """Return the ladder that should draw the housing card, or None.

    Widest price spread first, then ``market_id`` as a total tiebreak so the
    result never depends on query order — the property #2674 found missing and
    the only one of the two that is a correctness claim.

    Returns ``None`` for an empty list; the route then publishes no
    distribution and the page renders no card, rather than a card whose numbers
    are a rescale of something that was never a distribution.
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (-_spread(c.probs), c.market_id),
    )
