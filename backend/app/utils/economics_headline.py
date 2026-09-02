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

__all__ = ["RecessionCandidate", "select_recession_headline"]


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
