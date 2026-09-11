"""#5246 — the price a settled contract is worth, written wherever it is graded.

A contract the venue has resolved is worth exactly 1 or exactly 0. Nothing else
can ever write those two values: `futures_price_refresh` refuses anything outside
`0 < prob < 1` by construction, and the venue stops quoting a `finalized` market
altogether (measured 2026-09-11 17:2xZ — every `finalized` leg of
`KXATP-26USO` returns `yes_bid: null, yes_ask: null, last_price: null`). So a
settled leg's price is not stale, it is UNREACHABLE, and the grader is the only
writer that will ever know it.

WHY THIS IS A SHARED CLAUSE AND NOT A LINE AT ONE CALL SITE (CERT-2637). The
first version of #5246 added the price to the settling UPDATEs in
`_resolve_winners_only` — which is RETIRED. The live graders are elsewhere:
`_backfill_kalshi_winners`, `_backfill_kalshi_winners_targeted`,
`_backfill_kalshi_winners_via_markets`, and the four-times-daily
`kalshi._backfill_from_settled_events`. Every one of them stamped
`api_settlement` and left the price behind, so the ship was inert on every path
a reader's row actually travels — and worse than inert once the price-refresh
refusal landed, because that made the residue those paths keep creating
permanently unreachable.

The lesson is the reason this module exists rather than a fourth copy of two
lines: **a settlement writer is a population, not a place.** Grep for the grade
(`api_settlement`), not for the statement you happened to read first, and give
the population one clause so a new writer inherits it instead of forgetting it.

`current_american_odds` goes to NULL rather than to a number: american odds for a
resolved contract are not a long price, they are undefined, and
`futures_price_refresh._KALSHI_RETIRE_DELISTED_SQL` already nulls the pair
together for the same reason.

NO CALIBRATION TRUTH MOVES. `opening_probability` and `calibration_probability`
are the curve's inputs (gotcha #144: the curve price is
`COALESCE(calibration_probability, opening_probability)`), neither is touched
here, and `futures_odds_snapshots` keeps the full price history either way. This
writes the one column that answers "what is this worth NOW", for a contract whose
answer is now known exactly.
"""

from __future__ import annotations

#: The stored type of `FuturesOutcome.current_probability`. Comparisons happen at
#: the precision the database actually keeps — see
#: `app/utils/price_change_stamp.py`, which exists because a provider float and
#: its rounded stored form are otherwise never equal.
_PRICE_TYPE = "numeric(7,6)"

#: The only two prices a settled contract can hold.
SETTLED_YES_PRICE = "1.0"
SETTLED_NO_PRICE = "0.0"


def settled_price_set_sql(price: str, alias: str = "fo") -> str:
    """SQL set-clause fragment writing the terminal price for a settled leg.

    Spliced into an `UPDATE futures_outcomes` that is already writing
    `is_winner` and `resolution_source = 'api_settlement'`, so the grade and the
    price land in one statement and cannot diverge.

    `price_changed_at` is maintained inline rather than through
    `price_change_stamp.price_changed_at_value` because these are raw `text()`
    UPDATEs, not Core set-clauses. The predicate is deliberately the same one —
    cast both sides to the column's stored type and stamp only when the write
    would actually change what is stored — so a leg already sitting at the
    settlement price is graded without being advertised as freshly moved (#2024).

    :param price: :data:`SETTLED_YES_PRICE` or :data:`SETTLED_NO_PRICE`. The value
        is interpolated, so the set of legal literals is closed by the raise
        below — including against a future caller that decides to pass a
        "probability we are fairly confident about".
    :param alias: the table alias the statement uses for `futures_outcomes`, or
        ``""`` for an unaliased `UPDATE futures_outcomes SET ...`. Postgres
        refuses a qualified column on the LEFT of a SET assignment, so only the
        read side is ever prefixed.
    """
    if price not in (SETTLED_YES_PRICE, SETTLED_NO_PRICE):
        raise ValueError(f"settlement price must be 0.0 or 1.0, got {price!r}")
    ref = f"{alias}.current_probability" if alias else "current_probability"
    stamp = f"{alias}.price_changed_at" if alias else "price_changed_at"
    return f"""
        current_probability={price},
        current_american_odds=NULL,
        price_changed_at=CASE
            WHEN {ref} IS DISTINCT FROM CAST({price} AS {_PRICE_TYPE})
            THEN NOW() ELSE {stamp} END
    """


def settled_price_values(is_winner: bool) -> dict:
    """The same clause for a Core/ORM `.values()` update.

    `price_changed_at` is NOT included: a Core update has
    `price_change_stamp.price_changed_at_value` available and that helper is the
    single maintained copy of the change predicate (#2024, "five price-writing
    sites across three poll tasks"). Callers on this path add it themselves so
    there is never a second Python implementation of it.
    """
    return {
        "current_probability": 1.0 if is_winner else 0.0,
        "current_american_odds": None,
    }
