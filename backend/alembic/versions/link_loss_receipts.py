"""A link that ENDS gets a receipt, and a market that settles gets a timestamp.

LINKLOSS-02, step 2 of the durable matching program (#2693). The reasoning is in
``app/utils/match_receipts.py`` (outcomes + actors) and
``app/utils/market_settlement.py`` (the stamp); this file is the DDL.

WHAT IT ADDS

* ``market_match_receipts.previous_event_id`` — where the link pointed before
  this attempt, so ``(prev, linked)`` reads as loss / move / attach.
* ``market_match_receipts.actor`` — ``matcher_pass`` | ``twin_cleanup`` |
  ``settlement`` | ``admin_repair``, the GROUP BY the link-loss census is.
* ``market_match_receipts.outcome`` widened 16 -> 32. The new
  ``superseded_by_twin_merge`` is 24 characters and does not fit the column the
  first migration created. Widening a ``varchar`` is a catalog-only change in
  PostgreSQL — no table rewrite, no scan — so it is safe in a release phase.
* ``futures_markets.settled_at`` — WHEN status became ``'resolved'``.

DEPLOY SAFETY (gotcha #31). Four ``ADD COLUMN``s with no default and no NOT
NULL, one ``varchar`` widening, and three index builds. The two receipt indexes
are over a table with days of rows at most. The third is on ``futures_markets``
(~450k rows), a plain non-concurrent btree over one nullable timestamp: seconds,
not minutes, and CONCURRENTLY is forbidden inside a migration here.

LOCK ORDER (#2782). ``futures_markets`` is taken FIRST and ``market_match_receipts``
second, because that is the order live code takes them
(``match_receipts.verify_links_are_durable`` reads the market, then flushes the
receipt — and the receipt's foreign key makes the market lock implicit anyway).
As first written this file did the opposite, and the inversion deadlocked four
Heroku releases (v4016-v4019, 2026-09-02) against ``match_prediction_markets``,
leaving production on stale code for ~50 minutes. The reordering is inert for
any database that already ran this revision — production is past it — and
reaches the identical end state on a fresh one; what it buys is that
``tests/test_migration_lock_order.py`` now has nothing to except. The rule and
the reasoning: ``app/utils/migration_lock_order.py``.

NOTHING IS BACKFILLED, AND THAT IS THE POINT. Every market resolved before this
release keeps ``settled_at IS NULL``. Stamping them with the release clock would
assert that hundreds of thousands of markets settled the moment the migration
ran — a fabricated timestamp in the one column added to stop a fabricated
answer. NULL means "we did not observe it", which is true, and the ``status``
column already answers "is it settled".

Revision ID: link_loss_receipts
Revises: match_receipts
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "link_loss_receipts"
down_revision = "match_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # futures_markets first: see LOCK ORDER in the module docstring (#2782).
    op.add_column(
        "futures_markets",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_futures_markets_settled_at", "futures_markets", ["settled_at"]
    )

    op.add_column(
        "market_match_receipts",
        sa.Column("previous_event_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "market_match_receipts",
        sa.Column("actor", sa.String(length=24), nullable=True),
    )
    # 'superseded_by_twin_merge' is 24 chars; the original column is 16.
    op.alter_column(
        "market_match_receipts",
        "outcome",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.create_index(
        "ix_match_receipt_outcome_actor",
        "market_match_receipts",
        ["outcome", "actor"],
    )
    op.create_index(
        "ix_match_receipt_prev_event",
        "market_match_receipts",
        ["previous_event_id"],
    )


def downgrade() -> None:
    # futures_markets first here too — a downgrade deadlocks the same way.
    op.drop_index("ix_futures_markets_settled_at", table_name="futures_markets")
    op.drop_column("futures_markets", "settled_at")
    op.drop_index(
        "ix_match_receipt_prev_event", table_name="market_match_receipts"
    )
    op.drop_index(
        "ix_match_receipt_outcome_actor", table_name="market_match_receipts"
    )
    # Narrowing back can only fail on a row this migration's own code wrote, and
    # a downgrade that leaves the widened column is harmless; but the pair must
    # be symmetric or the orphan-check guard flags it.
    op.alter_column(
        "market_match_receipts",
        "outcome",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.drop_column("market_match_receipts", "actor")
    op.drop_column("market_match_receipts", "previous_event_id")
