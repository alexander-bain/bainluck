"""`futures_outcomes.is_winner` is NULLABLE, in the model as well as in production.

## Why this file exists, stated as the defect it catches

Production has always had `is_nullable = YES` with a `false` default. The model
declared

    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)

and SQLAlchemy infers `nullable=False` from a non-Optional `Mapped[T]`. So
`Base.metadata.create_all` — which is how **every** real-Postgres gate in this
repo builds its schema — produced the column **NOT NULL**.

The consequence is not cosmetic. Three separate rules turn on the difference
between "graded a loss" and "nobody graded this":

* 12-CAL's `graded` column counts `is_winner IS NOT NULL` precisely because
  "not a winner" spans both;
* gotcha #21 forbids publishing unknown truth as a confident loss;
* Queue 299 rung 1b excludes a one-outcome market with zero affirmative grades.

**A metadata-built test database could not represent the state all three are
about.** A fixture seeded into one would prove those rules work by never
exercising them — and `test_calibration_vm_variant_join_pg.py` had to hand-patch
the column with an `ALTER ... DROP NOT NULL` to seed its own case at all.

CAL-P155 found the drift, CAL-P156 audited its blast radius (ten gates build
schema from metadata AND touch `is_winner`; only that one ever made a nullability
claim, and it had already diagnosed the problem itself), and Alex authorised the
model fix as its own queue — `runner-inbox/calibration/910`.

## What this is NOT

**Not a data change and not a migration.** Production is already nullable, so
there is nothing to alter there; this makes the *model* tell the truth about it.
No writer changes behaviour — `default=False` still fires for unsettled rows,
including when `None` is passed explicitly.

These assertions read SQLAlchemy's own column metadata, which is exactly what
`create_all` emits DDL from, so no database is needed to prove the property.
"""

from __future__ import annotations


def _column():
    from app.models.models import FuturesOutcome

    return FuturesOutcome.__table__.c.is_winner


def test_is_winner_is_nullable_in_the_model_because_production_is():
    """The whole fix, in one assertion.

    If this fails, `create_all` is once again building the column NOT NULL and
    no metadata-built test database can express "nobody graded this".
    """
    assert _column().nullable is True, (
        "futures_outcomes.is_winner is NOT NULL in the model while production "
        "has is_nullable = YES. Every gate that builds its schema from this "
        "model is now unable to represent ungraded truth, which is the "
        "distinction 12-CAL, gotcha #21 and Queue 299 rung 1b all rest on."
    )


def test_the_annotation_and_the_column_agree():
    """`nullable=True` under a `Mapped[bool]` annotation is a trap, not a fix.

    SQLAlchemy honours the explicit `nullable=True`, so the column would be
    correct — but every reader of the attribute, and every type checker, would
    be told the value can never be None. Pinned so the two cannot drift: the
    next person to touch this must move both.
    """
    from typing import get_args

    from app.models.models import FuturesOutcome

    ann = FuturesOutcome.__annotations__["is_winner"]
    # `Mapped[Optional[bool]]` -> unwrap Mapped, then check the Optional.
    inner = get_args(ann)[0]
    assert type(None) in get_args(inner), (
        f"is_winner is annotated {ann!r}; the column is nullable, so the "
        f"annotation must be Mapped[Optional[bool]] or every reader is told a "
        f"None it can actually receive is impossible"
    )


def test_unsettled_is_still_stored_as_false():
    """The widening must not turn every ingest write into a NULL.

    NULL means "nobody graded this". Unsettled-but-tracked is FALSE, and that is
    what every writer produces by taking the column default. If this default
    ever disappears, ordinary polling starts manufacturing unknown truth and
    rung 1b will begin excluding live markets from the curve.
    """
    col = _column()
    assert col.default is not None, "the False default is gone"
    assert col.default.arg is False, (
        f"the column default is {col.default.arg!r}, not False — unsettled rows "
        f"would no longer be distinguishable from ungraded ones"
    )


def test_nothing_else_in_this_table_claims_a_nullability_it_cannot_have():
    """The class, not just the instance — every non-Optional column is NOT NULL.

    `is_winner` was not special; it was simply the one whose NOT NULL happened to
    collide with a rule that needed NULL. Any other non-Optional `Mapped[T]` on
    this table carries the same silent `nullable=False`, so this enumerates them
    rather than leaving the next collision to be found by a blocked cert.

    This is a LEDGER, deliberately not a prohibition. A NOT NULL column is
    usually right; what is not acceptable is being unaware of one. If this list
    changes, decide whether production agrees before editing the expectation.

    ⚠️ **It is a MODEL-side ledger.** It reads `__table__`, so it says what
    `create_all` will build — not what production has. CI has no production
    connection, so nothing here can re-check that; the value is that a future
    divergence becomes a failing test instead of a surprise four sessions later.

    🔴 **THE TWO WERE COMPARED BY HAND FOR THIS QUEUE, AND THERE IS A SECOND
    DIVERGENCE THAT IS DELIBERATELY LEFT ALONE.** Measured 2026-08-31 against
    `information_schema.columns`:

        production NOT NULL : external_id, id, market_id, name
        model      NOT NULL : external_id, id, last_updated, market_id, name
        is_winner (prod)    : is_nullable = YES, default false   <- fixed here

    **`last_updated` is NOT NULL in the model and NULLABLE in production** — the
    same drift class as `is_winner`, found by running this comparison rather
    than by assuming `is_winner` was unique. It is NOT changed here: Alex
    authorised `is_winner` specifically (`runner-inbox/calibration/910`), no rule
    depends on `last_updated` being absent, and widening it would retype every
    reader of a timestamp for no named ship. **Reported, not smuggled.** The
    ledger below therefore encodes the MODEL's set including `last_updated`, and
    this paragraph is why that is not an oversight.
    """
    from app.models.models import FuturesOutcome

    not_null = sorted(
        c.name for c in FuturesOutcome.__table__.c if not c.nullable
    )
    assert not_null == [
        "external_id",
        "id",
        "last_updated",
        "market_id",
        "name",
    ], (
        f"the NOT NULL set on futures_outcomes changed to {not_null}. That is "
        f"not necessarily wrong — but every name here is a state a "
        f"metadata-built test database cannot represent as absent, so confirm "
        f"production agrees before updating this list."
    )
    assert "is_winner" not in not_null
