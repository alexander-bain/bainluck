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

Second rule, same thesis — **a duplicate condition leg is not a gradeable
outcome** (Q487). One Polymarket condition can land on a market twice under two
external_id conventions: the bare ``{condition_id}`` row written by the field
writer, and a ``{condition_id}_yes`` / ``{condition_id}_no`` pair written by the
sub-market writer. When both conventions sit on the SAME market, the ``_no`` leg
is the *negation of one named candidate*, not a candidate — and it prices near
1.00 whenever that candidate loses.

Measured on production 2026-09-01, market 59835854 *"Which cities face tornado
risk on August 30?"*: ``0x2f2d…1733`` is **Chicago, IL** at 0.0245, and its
duplicate ``0x2f2d…1733_no`` sits at **0.974 and is ``is_winner = true``** — so
"No" is crowned the winner of a 25-city field market, and all 25 real cities are
stamped losers. **235 such rows across 217 polymarket ``field`` markets.**

The leg does two distinct harms and the predicate below has to stop both:

1. It *supplies the terminality* that makes an ungraded field look cleanly
   resolved. Without the contaminant those 26 rows are all ≤0.05 — nothing to
   crown. The single ≥0.95 leg is the contaminant itself, so
   ``INCOHERENT_FIELD_HAVING_SQL`` (which needs **more than one**) never fires.
2. It *receives* the winner stamp, and the market then drops out of the
   authoritative re-settlement net (``_backfill_polymarket_winners`` only
   re-examines markets holding a source outside
   ``('api_settlement', 'clean_resolution')``), so the wrong grade is permanent.

Excluding the leg restores the counterfactual — the market grades exactly as it
would have if the duplicate had never been ingested. That is deliberately not a
new policy; inventing one here would be guessing.
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

# The suffixes the sub-market writer appends to a condition id. Both legs of the
# pair are duplicates when the bare condition id is also on the market — the
# ``_no`` leg is the one that gets crowned, but the ``_yes`` leg is equally not a
# candidate and equally must not supply terminality.
DUPLICATE_CONDITION_LEG_SUFFIXES = ("_yes", "_no")


def strip_condition_leg_suffix(external_id: str | None) -> str | None:
    """``"0xabc_no"`` -> ``"0xabc"``. Returns ``None`` when there is no suffix.

    ``None`` means "this row cannot be a duplicate leg", which is a different
    answer from "this row is a leg whose twin is absent" — callers need to tell
    those apart, so this does not fall back to returning the input unchanged.
    """
    if not external_id:
        return None
    for suffix in DUPLICATE_CONDITION_LEG_SUFFIXES:
        if external_id.endswith(suffix):
            return external_id[: -len(suffix)]
    return None


def is_duplicate_condition_leg(external_id: str | None, sibling_external_ids) -> bool:
    """True iff this row is a ``_yes``/``_no`` leg of a condition ALSO on the market.

    ``sibling_external_ids`` is every external_id on the same market (including
    this one — a row is never its own stripped twin, so passing it is harmless).

    Both halves are required. A ``_yes``/``_no`` row on a market that does NOT
    also carry the bare condition id is the ordinary sub-market shape and is a
    perfectly real outcome; suppressing it would delete working markets.
    """
    stripped = strip_condition_leg_suffix(external_id)
    if stripped is None:
        return False
    return stripped in set(sibling_external_ids)


# Row-level SQL mirror of ``is_duplicate_condition_leg``, for the graders. A
# predicate over a single ``fo`` row, usable in a WHERE (unlike
# ``INCOHERENT_FIELD_HAVING_SQL``, which is an aggregate HAVING clause).
#
# The cheap suffix test is written FIRST so the planner can skip the correlated
# lookup for the overwhelming majority of rows, which carry no suffix at all.
# ``regexp_replace`` is only ever evaluated inside the EXISTS.
DUPLICATE_CONDITION_LEG_SQL = """NOT (
    (right(fo.external_id, 4) = '_yes' OR right(fo.external_id, 3) = '_no')
    AND EXISTS (
        SELECT 1 FROM futures_outcomes dup_twin
        WHERE dup_twin.market_id = fo.market_id
          AND dup_twin.external_id
              = regexp_replace(fo.external_id, '_(yes|no)$', '')
    )
)"""
