"""When the sportsbooks disagree, the median stops summarising and starts inventing (#7523).

`_ingest_event_odds` publishes `statistics.median(...)` of every book's
de-vigged home probability as the sportsbook consensus. #1841 chose the median
over the mean deliberately and correctly — a mean lets one straggling book carry
the number as the others drop out. But the median has a failure mode of its own
that #1841 had no specimen for:

**with an even number of readings the median INTERPOLATES the two middle ones.**

While every book agrees that is harmless — the two middle readings are a point
apart and their midpoint is a reading too. The moment the market splits it is
not. A goal lands, three books reprice and three have not yet, and the median
returns the empty middle of a bimodal set: the one value the evidence most
strongly excludes, and the value a reader reads as "even game".

MEASURED, production 2026-09-20 14:46Z, event 15305946 (Brest @ Auxerre, live,
85', Auxerre leading 2-1), served as the TOP CARD of Discover at `score 98`:

    sorted book readings  [0.164, 0.176, 0.200, 0.801, 0.801, 0.934]
    median                (0.200 + 0.801) / 2  =  0.5005
    published             betting 0.5005, betting_book_count 6
    rendered              "Auxerre 50%"

Six books, and not one of them quoted 50%. Kalshi's verified live speaker said
0.84 in the same bag.

Normal disagreement is nowhere near this. All live events with book coverage at
14:58Z, latest reading per book: the gap between the two middle readings has
median 0.0080 and p90 0.0153 — books agree to about a point — while 2 of the 16
even-count events sat above 10 points, mid-move. So the threshold below is not
cutting into the ordinary case; it is naming a market caught between two prices.

THE RULE, in ruling 051's grammar. That ruling drops the sportsbook consensus
below its book floor because "nothing downstream can tell 'the books say 13%'
from 'the books SAID 13% before they stopped'". The same sentence answers this:
nothing downstream can tell "the books say 50%" from "the books say 20% and 80%
and we split the difference". A split market is not a consensus, and the honest
representation of "they have not agreed yet" is the key's absence, exactly as it
is for a market that has thinned.

`statistics.median_low` was the obvious cheaper fix — it always returns a value
some book actually quoted — and it is wrong here: on the 3/3 split above it
returns 0.200, so the card would print 20% for a team leading 2-1. Between an
invented number and a real-but-superseded one, neither is the answer.

ODD COUNTS ARE OUT OF SCOPE BY CONSTRUCTION, not by oversight: with an odd
number of readings the median IS one of the readings, so nothing is invented.
Such a value can still be the stale cluster's, which is a different defect (a
quoted price that has been overtaken) and needs its own specimen before it gets
its own rule.
"""

from __future__ import annotations

from typing import Optional, Sequence

__all__ = ["CONSENSUS_SPLIT_GAP", "median_invents_its_answer"]

#: How far the two middle readings may sit apart before the median's
#: interpolation stops being a summary of the books and becomes a number none of
#: them quoted. 10 points, against a measured p90 of 1.5 points (see above), so
#: ordinary book-to-book noise cannot reach it.
CONSENSUS_SPLIT_GAP = 0.10


def median_invents_its_answer(
    readings: Sequence[float],
) -> Optional[tuple[float, float]]:
    """The two middle readings, when the median between them is nobody's price.

    Returns ``(lower, upper)`` — the pair the median would interpolate — when
    the reading set is even-sized and that pair disagrees by more than
    :data:`CONSENSUS_SPLIT_GAP`. Returns ``None`` when the median is safe to
    publish, which covers three separate cases and the caller needs none of
    them distinguished:

    * an odd count, where the median is itself one of the readings;
    * an even count whose middle pair agrees, where the midpoint is as good a
      summary as either of them;
    * fewer than two readings, where there is nothing to interpolate.

    ``None`` here means "the median is a summary", NOT "the books are healthy".
    Whether there are enough books at all is ruling 051's question and is asked
    separately.
    """
    values = sorted(float(reading) for reading in readings)
    if len(values) < 2 or len(values) % 2:
        return None
    middle = len(values) // 2
    lower, upper = values[middle - 1], values[middle]
    if upper - lower <= CONSENSUS_SPLIT_GAP:
        return None
    return lower, upper
