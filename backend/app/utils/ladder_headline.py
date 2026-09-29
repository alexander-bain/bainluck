"""The rung a cumulative ladder's headline quotes — one rule for every surface.

#9283 gave the `/weather` card this rule; #9531 is its market page, one tap
away, still quoting the loosest rung. Production 2026-09-29 02:49Z,
`/futures/59699693` at 390px:

    Hurricane Polo category?   100%  Category 1 or above

while the `/weather` card that links there read ">99% Category 5 or above".
Polo is a Category 5 storm and all five rungs are priced at 99.5%; the page's
price-leader scan took the first of a five-way tie. So the rule lives here and
both surfaces ask it, rather than the page growing a second copy that drifts.

The rule itself is #9283's, unchanged: walk the priced rungs from the loosest,
keep going while each is still >= 50%, quote the last. The walk stops at the
first rung under 50% rather than jumping to a later rung over it, so an
incoherent ladder (1+ 90%, 2+ 30%, 3+ 60%) is never read as "3+ is likely".
Unpriced rungs take no part. No priced rung >= 50% returns None, and the
caller's ordinary leader stands.
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

from app.utils.ladder_monotonicity import DEC, cumulative_outcome_ladder


def ladder_median_row(
    rows: Sequence[Mapping[str, object]],
    *,
    question: Optional[str],
    probability: Callable[[Mapping[str, object]], Optional[float]],
) -> Optional[Mapping[str, object]]:
    """The tightest rung the ladder still calls likely, or None.

    ``rows`` carry ``"name"``; ``probability`` reads a row's 0-1 price (None =
    unpriced). The grammar is `cumulative_outcome_ladder` with dates and the
    question, exactly as the `/weather` card has read it since #9284.
    """
    ladder = cumulative_outcome_ladder(rows, dates=True, question=question)
    if ladder is None:
        return None
    rungs, direction = ladder
    priced = [(value, row) for value, row in rungs if probability(row) is not None]
    # Loosest first: the lowest threshold of an "above" ladder, the latest
    # date of a "by" ladder.
    priced.sort(key=lambda pair: pair[0], reverse=(direction != DEC))
    median = None
    for _value, row in priced:
        if float(probability(row)) < 0.5:
            break
        median = row
    return median


def ladder_headline_outcome_id(
    outcomes: Sequence[Mapping[str, object]],
    question: Optional[str],
) -> Optional[int]:
    """The served outcome a market page's hero should quote instead of its leader.

    ``outcomes`` are the detail payload's served rows (``id``, ``name``, 0-1
    ``probability``). Returns the median rung's id only when it is NOT the row
    the clients already hero — the first row at the top price, unpriced as 0,
    which is the web page's `leader` sort and the unfurl's. Every board whose
    headline is already right therefore serves None and renders byte-identically;
    only the boards quoting a looser rung than the market's answer move.
    """
    median = ladder_median_row(
        outcomes, question=question, probability=lambda row: row.get("probability")
    )
    if median is None:
        return None
    leader = max(outcomes, key=lambda row: row.get("probability") or 0.0)
    if median is leader:
        return None
    return median.get("id")
