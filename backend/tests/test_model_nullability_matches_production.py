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

## 🔴 NULLABILITY WAS ONLY HALF OF IT — CERT-521 [P1]

The first attempt at this fix (`b3e46d34`) widened the column and stopped there.
It was **blocked**, correctly. Production's DDL is `boolean NULL DEFAULT false`;
the model carried a *client-side* `default=False`, which only fires on an ORM
insert. So the compiled PostgreSQL DDL was

    is_winner BOOLEAN,

with no `DEFAULT`. Before the widening, a raw `INSERT` omitting the column failed
loudly against the NOT NULL. After it, the same statement would have stored
**NULL in a metadata-built test database and FALSE in production** — and raw
`INSERT` is exactly how the real-Postgres gates here seed. A gate could then
manufacture "ungraded truth" out of a field it simply forgot to name. That is the
test/prod semantic split this file exists to close, re-opened one layer down.

`tests/test_pg_gate_seed_completeness.py` already names the asymmetry as its own
reason to exist: *a raw INSERT bypasses SQLAlchemy's Python-side `default=`, so a
column carrying one is NOT excused; only a `server_default` is.*

So parity here means **three** facts, not one, and each has its own assertion
below: nullable, client default False, server default `false`. The compiled DDL
is asserted as well, because the first two can be individually right while the
statement `create_all` actually emits is still wrong — which is precisely how the
first attempt went green.

## What this is NOT

**Not a data change and not a migration.** Production is already nullable with a
`false` server default (the migration that built it, `add_futures_tables.py`,
declared `server_default='false'`), so there is nothing to alter there; this makes
the *model* tell the truth about it. No writer changes behaviour — `default=False`
still fires for unsettled rows, including when `None` is passed explicitly.

These assertions read SQLAlchemy's own column metadata and the DDL it compiles,
which is exactly what `create_all` emits, so no database is needed to prove the
property. The behaviour those emitted columns then have against a real server —
raw insert omitted reads FALSE, explicit NULL stays NULL — is proved separately
and with a real Postgres in
`tests/integration/test_futures_outcome_grade_schema_parity_pg.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

#: Prose spellings of "this column cannot be NULL". Deliberately NOT the SQL
#: `IS NOT NULL`, which is a correct null-safe predicate and appears all over the
#: calibration queries — the thing being hunted is a sentence a reader believes,
#: not an operator.
_CLAIM_RE = re.compile(r"non-nullable|non-null |NOT NULL boolean|NOT NULL with")

#: The one site left saying it, and why. `precompute_calibration.py` is the
#: freeze-lift's hot file on the unmerged `program/calibration-119` stack, and a
#: comment edit there would conflict with a branch that is pending cert. The
#: claim is wrong but inert: rung 1's discriminator is winner CARDINALITY, and
#: the surrounding rungs key on `resolution_source`. Delete this entry when the
#: lift merges — an allowlist that outlives its reason is the next stale comment.
_KNOWN_STALE = {"tasks/precompute_calibration.py"}


def test_no_app_comment_still_says_is_winner_cannot_be_null():
    """The model told the truth; the prose around it has to as well.

    CERT-521 found six comments asserting `is_winner` is non-nullable — the exact
    premise this queue disproves. They are not runtime bugs (their guards key on
    `resolution_source`), but they are how the drift comes BACK: the next reader
    takes the sentence, not the schema, and re-derives `Mapped[bool]`.

    This lane has been blocked twice in three sessions by documentation read as
    truth (CAL-P154's docstring, CAL-P155's comment-quoting CTE guard). So the
    correction is pinned as a ratchet rather than left as a claim in a report.
    """
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = path.relative_to(APP_DIR).as_posix()
        if rel in _KNOWN_STALE:
            continue
        source = path.read_text()
        for match in _CLAIM_RE.finditer(source):
            window = source[max(0, match.start() - 240) : match.end() + 240]
            if "is_winner" in window:
                line = source[: match.start()].count("\n") + 1
                offenders.append(f"{rel}:{line}")

    assert not offenders, (
        f"these comments still say futures_outcomes.is_winner cannot be NULL, "
        f"which the model and production both contradict: {offenders}. Fix the "
        f"sentence — the reasoning around it usually survives, because "
        f"production still STORES False rather than NULL for an ungraded row "
        f"(2,536 NULL of 3,893,126, measured 2026-08-31)."
    )


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


def test_the_server_default_is_productions_server_default():
    """CERT-521 [P1]. The half the first attempt missed.

    A client-side `default=` is invisible to `text("INSERT ...")`, which is how
    every real-Postgres gate in this repo seeds. Production fills an omitted
    `is_winner` with FALSE because its DDL says `DEFAULT false`; a metadata-built
    database with only the Python default would have stored NULL. Same statement,
    two different truths, and the NULL one is the state gotcha #21 forbids
    publishing as a loss.
    """
    col = _column()
    assert col.server_default is not None, (
        "futures_outcomes.is_winner has no server_default while production's "
        "DDL is `DEFAULT false`. A raw INSERT that omits the column now stores "
        "NULL in a metadata-built test database and FALSE in production — the "
        "test/prod split this file exists to close, one layer down."
    )
    rendered = str(col.server_default.arg).strip().strip("'").lower()
    assert rendered == "false", (
        f"the server default renders {rendered!r}, not 'false'. Production's "
        f"`information_schema.columns.column_default` is exactly `false` "
        f"(measured 2026-08-31)."
    )


def test_the_compiled_postgres_ddl_is_the_production_ddl():
    """The three facts above can each be right while the emitted DDL is wrong.

    That is not hypothetical — it is how `b3e46d34` went green with four passing
    metadata guards and still compiled `is_winner BOOLEAN,`. `create_all` runs
    the compiler, not the attributes, so the compiler is what gets asserted.

    Production, read from `information_schema.columns` on 2026-08-31:
    `data_type = boolean`, `is_nullable = YES`, `column_default = false`.
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.models.models import FuturesOutcome

    ddl = str(
        CreateTable(FuturesOutcome.__table__).compile(dialect=postgresql.dialect())
    )
    line = next(
        (
            ln.strip().rstrip(",").strip()
            for ln in ddl.splitlines()
            if ln.strip().startswith("is_winner ")
        ),
        None,
    )
    assert line is not None, (
        f"no is_winner column in the compiled CREATE TABLE — the guard cannot "
        f"see the thing it grades:\n{ddl}"
    )
    assert line == "is_winner BOOLEAN DEFAULT false", (
        f"`create_all` emits {line!r}. Production is "
        f"`boolean NULL DEFAULT false`; anything else means a metadata-built "
        f"test database disagrees with the server the writers actually run "
        f"against."
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
