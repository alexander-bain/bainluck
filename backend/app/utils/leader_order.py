"""UX-P276 / #2789 — a truncated outcome list must keep its leader.

The `/sports` prop cards stamp a rank badge `1 2 3 4 5` and a highlighted
"leader" treatment on the first five outcomes of a market. Nothing on the path
sorted them:

* `FuturesMarket.outcomes` (``models.py``) declares no ``order_by=``, so a
  ``selectinload`` returns rows in whatever order Postgres produced them;
* `/api/futures/grouped-feed` then shipped ``m["outcomes"][:5]`` — five rows off
  the front of an unordered array;
* the renderer stamped ``rank={index + 1}`` on that.

So the badge was a claim the data never made. Measured on the live `/sports`
shape before this shipped: **0 of 5** five-outcome cards led with their
favourite, and the 192-golfer "Omega European Masters - Winner" card led with a
0.09% golfer while the true leader at 11.8% was not on the card at all.

This is the same rule the frontend states in `lib/discover/leaderOrder.ts`
(UX-P007 / #1526) — *sort at the truncation site, do not trust the incoming
order* — and the same thing `get_futures_detail` already does inline for its own
``top_outcomes`` (``routes/futures.py``, ``sorted(..., reverse=True)[:5]``).
Naming it once means both truncation sites can be pointed at one rule instead of
each re-deriving it.

The module imports nothing and must stay that way (zero circular-import risk).
"""

from typing import Any, Optional, Sequence


def _probability_of(outcome: Any) -> Optional[float]:
    """Read an outcome's probability from a dict row or an ORM row.

    The grouped feed builds plain dicts; other call sites hold ORM objects whose
    column is ``current_probability`` with ``probability`` as a property alias.
    Both are accepted so a future call site cannot pick the wrong accessor and
    silently sort every row equal.
    """
    if isinstance(outcome, dict):
        value = outcome.get("probability")
        if value is None:
            value = outcome.get("current_probability")
    else:
        value = getattr(outcome, "probability", None)
        if value is None:
            value = getattr(outcome, "current_probability", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        # A probability we cannot read is not evidence that this row leads.
        return None


def leader_first_outcomes(outcomes: Sequence[Any]) -> list:
    """Leader-first copy of ``outcomes``, highest probability first.

    Stable: equal probabilities keep their incoming relative order, so an
    upstream tie-break (alphabetical, ladder position, a `rank` column) survives
    rather than being scrambled. Unpriced rows (``None``, or a value that will
    not parse) sort **last** — an outcome nobody has quoted is never the leader,
    and it must not tie with a genuine 0.0 the way ``key=lambda o: p or 0``
    would.

    Never mutates the input. Idempotent, so a call site whose upstream already
    sorts is unaffected — which is what makes it safe to apply at a shared
    renderer rather than only at the one broken producer.
    """

    def sort_key(pair):
        index, outcome = pair
        probability = _probability_of(outcome)
        if probability is None:
            # Bucket 1 sorts after every priced row regardless of magnitude.
            return (1, 0.0, index)
        # Negating rather than passing reverse=True keeps the index term
        # ASCENDING, which is what makes ties stable in the incoming order —
        # reverse=True would invert them.
        return (0, -probability, index)

    return [outcome for _, outcome in sorted(enumerate(outcomes), key=sort_key)]
