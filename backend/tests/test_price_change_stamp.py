"""#2024 — the `price_changed_at` predicate, asserted on the SQL it compiles to.

There is no local PostgreSQL in this sandbox (`initdb` dies on `shmget`), so a
round-trip test is CI-only. What can be proven here is the thing that actually
went wrong in the design — the SHAPE of the emitted SQL — and it is worth
proving because two of the three failure modes are silent:

  * comparing against `excluded.` instead of the existing row makes the
    predicate vacuously false, so the column never advances;
  * comparing a float against a `Numeric(7, 6)` column at the PROVIDER's
    precision makes it vacuously true, so the column advances on every poll of
    an unmoved market — which reproduces #2024's defect in the new column while
    looking like the fix;
  * `!=` instead of `IS DISTINCT FROM` swallows every NULL transition, and a
    price going away is exactly the transition that matters most.

None of the three raises. All three are visible in the compiled string.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.models.models import FuturesOutcome
from app.utils.price_change_stamp import price_changed_at_value


def _sql(value: object) -> str:
    expr = price_changed_at_value(
        FuturesOutcome.current_probability,
        FuturesOutcome.price_changed_at,
        value,
    )
    return str(
        expr.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_it_compares_the_existing_row_not_the_proposed_value() -> None:
    """Inside ON CONFLICT DO UPDATE a bare column IS the existing row.

    If this ever renders `excluded.current_probability`, the predicate compares
    the incoming value to itself, is never true, and the column silently freezes
    at whatever it held when the row was inserted.
    """
    sql = _sql(0.42)
    assert "futures_outcomes.current_probability" in sql
    assert "excluded" not in sql.lower()


def test_it_is_distinct_from_not_equality() -> None:
    """A price going AWAY is a change, and `!=` cannot see it.

    `NULL != 0.42` is NULL, which is not true, so an equality predicate leaves
    the stamp untouched on exactly the transition a consumer most wants to know
    about. Kalshi's unprice path writes `current_probability = NULL`.
    """
    sql = _sql(0.42)
    assert "IS DISTINCT FROM" in sql.upper()
    assert "!=" not in sql


def test_both_sides_are_cast_to_the_STORED_precision() -> None:
    """The trap that would have made the whole column useless.

    `current_probability` is `Numeric(7, 6)`. A Polymarket midpoint arrives as
    `0.0512345678` and is STORED as `0.051235`; on the next poll the same
    unchanged price compares DISTINCT against the stored value unless both sides
    are taken to the same precision first. The column would then stamp on every
    poll — i.e. it would mean precisely what `last_updated` already means.
    """
    sql = _sql(0.0512345678)
    # Two casts, one per side, both to the column's own type.
    assert sql.upper().count("CAST(") == 2
    assert sql.upper().count("NUMERIC(7, 6)") == 2


def test_the_unchanged_branch_keeps_the_EXISTING_stamp() -> None:
    """`else_` is the row's own value, never NULL and never `now()`.

    An `else_=None` would blank the stamp on every quiet poll — worse than not
    having the column, because it would read as "this price has never moved".
    """
    sql = _sql(0.42)
    assert "ELSE futures_outcomes.price_changed_at" in sql
    assert sql.upper().count("NOW()") == 1


def test_a_none_price_still_produces_a_real_comparison() -> None:
    """The unprice path. `None` is a value here, not a reason to skip.

    Kalshi nulls out the price of an outcome that stopped being quoted. That is
    a change if it had one and a no-op if it did not, and `IS DISTINCT FROM
    NULL` distinguishes those two — which is the whole reason the helper does
    not short-circuit on `None`.
    """
    sql = _sql(None)
    assert "IS DISTINCT FROM" in sql.upper()
    assert "NULL" in sql.upper()
    assert "futures_outcomes.current_probability" in sql


def test_the_column_it_writes_accepts_what_it_writes() -> None:
    """A cheap end-to-end sanity check on the pairing of helper and column."""
    col = FuturesOutcome.__table__.c.price_changed_at
    assert col.nullable is True
    # Rendered against the real dialect: generic `DateTime` stringifies as
    # "DATETIME", which says nothing about what PostgreSQL will hold. The
    # timezone matters — every consumer compares it to `now()`.
    assert str(col.type.compile(postgresql.dialect())) == "TIMESTAMP WITH TIME ZONE"
