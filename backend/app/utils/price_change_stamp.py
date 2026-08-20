"""#2024 — `price_changed_at`, and the one expression that maintains it.

UX-P106 audited `futures_outcomes.last_updated` and REFUSED the migration-free
fix. The finding, restated because it is the whole reason this module exists:

    `app/routes/playoffs.py` reads that column as a LIVENESS gate — an outcome
    whose stamp predates the cutoff is `continue`d and does not render. Making
    the stamp conditional would therefore blank every merely-STABLE price out of
    the playoff grid: a team parked at 3% for a week disappears. Meanwhile
    `app/routes/admin_judgments.py` reads the SAME column as a price-age floor.
    Two readings, one column, no value that satisfies both.

So the column is not narrowed. A new one is added beside it, this is what
writes it, and `last_updated` keeps meaning exactly what the playoff grid
already believes it means.

── WHY A SHARED HELPER AND NOT FIVE COPIES ──────────────────────────────────

There are five price-writing sites across three poll tasks, and #1951 is the
standing lesson about what a third copy of a predicate costs: that issue WAS a
third copy of the feed's admission rule, in no parity test, silently carrying a
stale arm. A change-detection predicate is worse than most, because a copy that
drifts does not throw — it just stops stamping, and the column quietly becomes
wrong for one provider while looking healthy for the others.

── THE PRECISION TRAP, WHICH IS THE REASON THIS IS NOT A ONE-LINER ──────────

`current_probability` is `Numeric(7, 6)`, so a price is stored ROUNDED to six
decimal places. The incoming value is a Python float from a provider, and
Polymarket midpoints in particular carry far more precision than that:

    stored     0.051235          (what the last poll rounded 0.0512345678 to)
    incoming   0.0512345678      (the same unchanged price, next poll)

Compared naively those are DISTINCT, so the column would stamp on every poll of
an unmoved market — reproducing, in a new column, the exact defect #2024 is
open on, while looking like it had been fixed. Both sides are therefore cast to
the column's own type before comparison, so the question asked is the only one
that can be answered honestly: *would this write change what is stored?*
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Numeric, case, cast, func, literal

#: The stored type of `FuturesOutcome.current_probability`. Comparisons happen
#: at the precision the database actually keeps, never at the provider's.
PRICE_NUMERIC = Numeric(7, 6)


def price_changed_at_value(current_col: Any, stamp_col: Any, new_probability: Any) -> Any:
    """`price_changed_at` for an ON CONFLICT DO UPDATE / UPDATE set clause.

    ``func.now()`` when this write would change the stored price, otherwise the
    row's existing stamp — so the column answers "when did this price last
    MOVE", which is the question `last_updated` cannot answer.

    :param current_col: the existing row's price column (``FuturesOutcome.
        current_probability``). Inside an ``ON CONFLICT DO UPDATE`` a bare
        column reference renders as the EXISTING row, which is what is wanted;
        ``excluded.`` would render the proposed value and make the comparison
        vacuously false.
    :param stamp_col: ``FuturesOutcome.price_changed_at`` — the value to keep
        when nothing moved.
    :param new_probability: the price about to be written. May be ``None``: a
        price going away IS a change, and ``IS DISTINCT FROM`` says so without
        the NULL-swallowing that ``!=`` would introduce.
    """
    return case(
        (
            cast(current_col, PRICE_NUMERIC).is_distinct_from(
                cast(literal(new_probability), PRICE_NUMERIC)
            ),
            func.now(),
        ),
        else_=stamp_col,
    )
