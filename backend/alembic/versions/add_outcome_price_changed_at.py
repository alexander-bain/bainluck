"""#2024 — futures_outcomes.price_changed_at

UX-P107, and the slot was assigned for it. UX-P106 audited the two futures
touch-stamps and refused the migration-free fix: `futures_outcomes.last_updated`
is read as a LIVENESS gate by `app/routes/playoffs.py` (a stale stamp `continue`s
the outcome out of the playoff grid) and as a PRICE-AGE floor by
`app/routes/admin_judgments.py`. No value the column can take serves both, so
the column is left alone and a purpose-built one is added beside it.

Nullable and populated FORWARD by the polls. No backfill: there is no historical
source for "when did this price last move" — the snapshots are sampled, not
change-triggered — and inventing one would be gotcha #53 written into a column.

── THE INDEX IS NOT IN THIS FILE, ON PURPOSE (gotcha #31) ───────────────────

UX-P106 measured, on production, that `futures_outcomes.last_updated` has NO
index: `EXPLAIN` on the sampler's own price-age predicate returns
**Seq Scan on futures_outcomes, total cost 156,591**, and three attempts at
#2024's census query timed out at 25 s for that reason.

It still does not go here. Gotcha #31 is a dated outage, not a style rule:
`CREATE INDEX CONCURRENTLY` inside a migration hangs Heroku's ~5-minute release
phase and takes the whole app down with it (the May 22 `odds_snapshots`
incident), and a NON-concurrent create on a table this size holds an ACCESS
EXCLUSIVE lock against the live pollers for the duration. Both failure modes
end the same way.

So the statement below is applied MANUALLY via psql, by the Integrator, as a
separate deploy step. It is idempotent and re-runnable:

    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_futures_outcomes_last_updated
        ON futures_outcomes (last_updated);

Two operational notes for whoever runs it, because a half-applied concurrent
index is the trap here:

  * run it OUTSIDE a transaction block — `CONCURRENTLY` cannot run inside one,
    and psql wraps `-1`/`--single-transaction` invocations;
  * if it fails partway it leaves an INVALID index behind that is never used and
    still costs writes. Check with
    `SELECT indexrelid::regclass, indisvalid FROM pg_index
      WHERE indexrelid = 'ix_futures_outcomes_last_updated'::regclass;`
    and `DROP INDEX CONCURRENTLY` before retrying.

`backend/tests/test_futures_stamp_semantics.py` asserts that this file does not
execute it, so the next person cannot quietly move it into the chain.

Revision ID: add_outcome_price_changed
Revises: add_disc_int_provenance
"""

from alembic import op
import sqlalchemy as sa

revision = "add_outcome_price_changed"
down_revision = "add_disc_int_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN with no default and no NOT NULL: a bare nullable add is a
    # catalog-only operation in PostgreSQL, so it does not rewrite the table and
    # cannot stall the release phase. A `server_default` would have been the
    # tempting way to avoid NULLs and is exactly what must not happen here — it
    # would stamp every historical row with the deploy time, which is a lie
    # about when its price last moved.
    op.add_column(
        "futures_outcomes",
        sa.Column("price_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_outcomes", "price_changed_at")
