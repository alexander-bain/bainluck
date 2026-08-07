"""Winner-field coherence — one rule, shared by capture, grading and the census.

A **mutually-exclusive** market is a single-winner partition: exactly one leg can
be true. Two invariants follow, and #1527 caught production violating both at once
on the same rows:

* **Capture.** The legs cannot all be near-certain. A 1X2 whose Home, Away *and*
  Draw all price at 1.00 sums to 300% — that is not a price, it is an upstream
  artifact, and stamping it as one poisons ``opening_probability`` permanently
  (a first observation is never re-opened, so a market first seen *after*
  settlement captures the settled price as its "opening" forever).
* **Grading.** At most one leg can be ``is_winner``. Three winners at
  ``current_probability = 1.0`` is a perfectly confident, perfectly wrong forecast
  filed three times into the calibration curve.

The rule lives here — not inlined at each site — because #1527's root cause *is*
drift between sites: ``_backfill_polymarket_winners`` grew this exact guard for the
Women's Wimbledon two-winner bug (Queue #167/#999) and its sibling
``_backfill_from_current_probability`` never did, so the class simply walked
through the sibling. CAL-P004's lesson, restated: producer and detector must not be
able to disagree about what the defect *is*.

Deliberately NOT covered — do not widen these without evidence:

* Markets that are not mutually exclusive. Independent binaries legitimately sum
  far past 100% (gotcha #23) — several teams can each be ~1.00 to make the
  playoffs. Every rule here is gated on mutual exclusivity for that reason.
* A *single* near-certain leg. That is what a settled or lopsided market looks
  like, and ``_resolve_market_probability`` is permissive at the extremes on
  purpose (a near-certain outcome legitimately has a cleared book).
"""
from __future__ import annotations

# The near-certainty bar. 0.95 is not a new number: it is the threshold
# ``_backfill_polymarket_winners`` and ``_backfill_from_current_probability``
# already price-crown at, so capture, grading and the census all agree on which
# legs count as "certain". Changing it here changes it everywhere, on purpose.
NEAR_CERTAIN_PROB = 0.95


def count_near_certain(probabilities) -> int:
    """How many legs are at or above the near-certainty bar (``None`` ignored)."""
    return sum(1 for p in probabilities if p is not None and p >= NEAR_CERTAIN_PROB)


def field_is_incoherent(probabilities, *, mutually_exclusive: bool) -> bool:
    """True when this field cannot be a real price for a single-winner partition.

    Requires BOTH mutual exclusivity and more than one leg at/above the bar. A
    one-leg field is never incoherent (nothing to contradict), and a non-mutex
    field is never judged here at all.
    """
    if not mutually_exclusive:
        return False
    probs = list(probabilities)
    if len(probs) < 2:
        return False
    return count_near_certain(probs) > 1


def winners_are_incoherent(winner_count: int, *, mutually_exclusive: bool) -> bool:
    """True when a single-winner partition has been crowned more than once."""
    return bool(mutually_exclusive) and winner_count > 1


# SQL fragment for the graders. Kept as a string rather than re-deriving the
# predicate in each query so the Python rule above and the SQL below cannot drift.
# Used inside a ``GROUP BY fm.id`` HAVING clause where ``fm`` is futures_markets
# and ``fo`` is futures_outcomes.
INCOHERENT_FIELD_HAVING_SQL = (
    "NOT (fm.mutually_exclusive"
    f"     AND COUNT(*) FILTER (WHERE fo.current_probability >= {NEAR_CERTAIN_PROB}) > 1)"
)
