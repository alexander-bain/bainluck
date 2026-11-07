"""#11929 PR-A: a store for venue price history, filled before the venue purges it.

THE SHIP. A settled futures market's chart keeps the price journey Kalshi held
for it. Kalshi deletes a settled market's candlesticks somewhere between 47 and
86 days after settlement (``app/utils/kalshi_retention.py``). This store keeps
them past that. Serving them on charts is PR-B; this revision only creates the
place they are kept.

WHAT THIS DOES, EXHAUSTIVELY. It creates two new, empty tables, their
constraints, and the b-tree indexes their primary and unique keys imply. It
writes no data, alters no existing table and adds no column. The indexes are
built on empty tables, so gotcha #31 (no ``CREATE INDEX CONCURRENTLY`` in a
migration) has nothing to apply to.

* ``venue_history_points``: one venue price per (outcome, venue timestamp).
  UNIQUE (outcome_id, observed_at) makes a rerun conflict instead of doubling.
  CHECKs refuse a probability outside (0, 1) and a non-positive resolution.
* ``venue_history_backfill_progress``: per (venue, market), which legs the
  writer has finished, so a run stopped by its wall budget resumes at the next
  leg and a market the venue keeps refusing is skipped after three attempts.

LOCKS. The one foreign key, ``venue_history_points.outcome_id`` →
``futures_outcomes.id``, takes SHARE ROW EXCLUSIVE on ``futures_outcomes`` while
it is added, so it briefly waits behind and blocks writers of that table.
``alembic/env.py`` arms ``lock_timeout`` and retries the batch (#2724). Nothing
scans ``futures_outcomes``: the new table is empty.

ENABLING NOTHING. Executing this turns nothing on. The only writer,
``app/tasks/venue_history_backfill.py``, returns before any read or venue call
unless ``VENUE_GAP_BACKFILL_ENABLED`` is set on ``bainluck-heavy``.

MIGRATION-CLASS (D45 / notice 47b). It lands only on Alex's word, through the
Integrator. No default fires on silence.

Reversible. The undo line is

    alembic downgrade events_fts_gin_fastupdate_off

which drops both tables and whatever they hold.

Revision ID: venue_history_points_11929
Revises: events_fts_gin_fastupdate_off
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "venue_history_points_11929"
down_revision = "events_fts_gin_fastupdate_off"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "venue_history_points",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "outcome_id",
            sa.Integer(),
            sa.ForeignKey("futures_outcomes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Numeric(7, 6), nullable=False),
        sa.Column("yes_bid", sa.Numeric(7, 6), nullable=True),
        sa.Column("yes_ask", sa.Numeric(7, 6), nullable=True),
        sa.Column("price_basis", sa.Text(), nullable=False),
        sa.Column("resolution_s", sa.Integer(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "outcome_id", "observed_at", name="uq_vhp_outcome_observed"
        ),
        sa.CheckConstraint(
            "probability > 0 AND probability < 1", name="ck_vhp_probability"
        ),
        sa.CheckConstraint("resolution_s > 0", name="ck_vhp_resolution"),
    )

    op.create_table(
        "venue_history_backfill_progress",
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "legs_done",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "points_inserted",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("venue", "market_id"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'done', 'failed')", name="ck_vhbp_status"
        ),
    )


def downgrade() -> None:
    op.drop_table("venue_history_backfill_progress")
    op.drop_table("venue_history_points")
