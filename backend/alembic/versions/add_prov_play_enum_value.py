"""Add `play` to the discover_provenance enum — the value the previous revision cannot add.

## The defect, in one sentence

`add_disc_int_provenance` **already ran in production**, so editing its enum
tuple to include `play` changes what a fresh database gets and changes nothing
whatsoever about the database that has the problem.

Re-verified against production on 2026-08-19, before writing this file:

    SELECT version_num FROM alembic_version;
    -- add_disc_int_provenance

    SELECT enumlabel, enumsortorder FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
     WHERE t.typname = 'discover_provenance' ORDER BY enumsortorder;
    -- user 1 | warmer 2 | sentinel 3 | gold_session 4 | admin 5 | unknown 6

Six values. `play` absent. Alembic runs a revision once, so `upgrade()` over
there can never execute again — and every Play interaction keeps being rejected
by PostgreSQL at commit while the ORM accepts it, which is the whole bug
`C-ADHOC-PROV-CORE P1` found.

A value that must appear in an already-migrated database needs a revision that
has not run yet. This is that revision. Lineage stays linear:

    add_typeahead_index -> add_disc_int_provenance -> add_prov_play_value

## Why `ADD VALUE` and not a type rebuild

The alternative — create `discover_provenance_new`, `ALTER TABLE … TYPE … USING`,
drop and rename — rewrites `discover_interactions` wholesale inside Heroku's
~5-minute release phase. That is gotcha #31's shape with a table rewrite instead
of an index, and the failure mode is a release that times out, which is a site
that does not deploy. `ADD VALUE` is a catalog insert: O(1), no table touched.

The price is that PostgreSQL has no `DROP VALUE`, which is what makes
`downgrade()` below a no-op rather than an inverse. That is stated there rather
than hidden.

## The transaction rule, and why the autocommit block is here anyway

Before PostgreSQL 12, `ALTER TYPE … ADD VALUE` could not run inside a
transaction block at all. Production is **PostgreSQL 17.10** (checked, not
assumed), where it can — the surviving restriction is only that the new label
may not be *used* in the same transaction, and this revision does not use it.

`autocommit_block()` is used regardless, for two reasons that outlive the
version check:

1. Alembic's own recommended form for `ADD VALUE`, so nobody has to re-derive
   the version matrix to review this file.
2. It keeps the statement correct if this chain is ever replayed against an
   older server — a restore, a developer's local instance, a future downgrade of
   the Heroku stack. The cost of the block is nothing; the cost of the
   assumption is a migration that raises `ALTER TYPE ... cannot run inside a
   transaction block` at release time.

`IF NOT EXISTS` makes it idempotent, which matters because `autocommit_block()`
means this statement is NOT rolled back if a later statement in the same
revision fails. There is no later statement today; the guard is what keeps that
from becoming a trap if one is ever added.

Revision ID: add_prov_play_value
Revises: add_disc_int_provenance
Create Date: 2026-08-19
"""

from alembic import op

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "add_prov_play_value"
down_revision = "add_disc_int_provenance"
branch_labels = None
depends_on = None

#: The one label this revision adds. Named as a constant because
#: `tests/test_discover_provenance.py` imports it to prove the CHAIN
#: (`add_disc_int_provenance.PROVENANCE_VALUES_AS_APPLIED` + this) equals the
#: receiver's allowlist in `app/utils/discover_provenance.py`. Binding the chain
#: rather than one file is the point: the previous binding held one migration
#: against the allowlist, which is exactly the assertion that stayed green while
#: the shipped enum diverged from both.
PLAY_VALUE = "play"

ENUM_NAME = "discover_provenance"


def add_value_sql(enum_name: str = ENUM_NAME, value: str = PLAY_VALUE) -> str:
    """The exact statement `upgrade()` executes, as a string.

    Exposed so the real-Postgres gate
    (`tests/integration/test_provenance_enum_real_postgres.py`) can run *this*
    statement rather than a hand-copied lookalike. A gate that re-spells the SQL
    it is verifying proves the gate's copy works — which is how the previous
    version of that file came to build its enum from the receiver's allowlist
    and then assert the result matched the receiver's allowlist.
    """
    return f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # `ALTER TYPE` is PostgreSQL-only. Every other dialect renders
        # SQLAlchemy's Enum as a VARCHAR + CHECK or as plain text, so there is no
        # catalog object to extend and nothing here to do. Returning is correct;
        # raising would break any sqlite-backed replay of the chain for a reason
        # that is not a defect.
        return

    with op.get_context().autocommit_block():
        op.execute(add_value_sql())


def downgrade() -> None:
    """Deliberate no-op. PostgreSQL cannot remove a value from an enum type.

    This is documented rather than silently empty because a silent no-op
    downgrade is indistinguishable from an unimplemented one, and the next
    reader would waste the same twenty minutes confirming it.

    There is no `ALTER TYPE … DROP VALUE` in any PostgreSQL release. Removing a
    label requires rebuilding the type and rewriting every column that uses it —
    the release-phase table rewrite `upgrade()` exists to avoid, and doing it in
    a *downgrade* is strictly worse, since a downgrade is what gets run under
    pressure during a rollback.

    The chain is still fully reversible, one step further down:
    `add_disc_int_provenance.downgrade()` drops the whole `discover_provenance`
    type, and `play` goes with it. So `downgrade -1` leaves a seven-value enum
    on a table that no longer has the column — harmless, and the next `upgrade`
    is a no-op here because of `IF NOT EXISTS` — while `downgrade -2` removes
    the type entirely. Nothing is stranded.
    """
    pass
