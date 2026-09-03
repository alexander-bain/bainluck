"""A link change is HISTORY — the append-only table beside the receipt.

LINKLOSS-03, the CERT-791 repair. The reasoning is on
``app.models.models.MarketLinkChange``; this file is the DDL.

WHY A SECOND TABLE INSTEAD OF MORE COLUMNS. LINKLOSS-02 put the link-change
vocabulary (``outcome``, ``previous_event_id``, ``actor``) on
``market_match_receipts``, which is one upserted row per market by design. A
market that was just unlinked sits at ``event_id IS NULL`` — the exact
population the scheduled matcher re-scans every 15 minutes — so the next
ordinary attempt overwrote all three columns and the reason a price left a card
was destroyed, typically within the hour. No column can fix that; a row that is
overwritten by design cannot also be history.

DEPLOY SAFETY (gotcha #31). One CREATE TABLE and three indexes on a table that
starts empty: milliseconds, and nothing to rewrite. No backfill exists to do —
the changes that already happened were overwritten, which is what this table
stops. The census reports from the first change written after this ships.

Revision ID: link_change_history
Revises: link_loss_receipts
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "link_change_history"
down_revision = "link_loss_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_link_changes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # No FK, on purpose: a twin cleanup deletes the event this row names,
        # and a market delete must not take the explanation with it.
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("market_name", sa.String(length=300), nullable=True),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=24), nullable=False),
        sa.Column("previous_event_id", sa.Integer(), nullable=False),
        sa.Column("new_event_id", sa.Integer(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # NO UNIQUE KEY ANYWHERE. The absence is the design: with nothing to
    # conflict on, ``INSERT`` is the only statement this table can take, and an
    # upsert cannot be added to a writer by accident later.
    op.create_index(
        "ix_link_change_changed_at", "market_link_changes", ["changed_at"]
    )
    op.create_index(
        "ix_link_change_prev_event",
        "market_link_changes",
        ["previous_event_id", "changed_at"],
    )
    op.create_index(
        "ix_link_change_market",
        "market_link_changes",
        ["market_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_link_change_market", table_name="market_link_changes")
    op.drop_index("ix_link_change_prev_event", table_name="market_link_changes")
    op.drop_index("ix_link_change_changed_at", table_name="market_link_changes")
    op.drop_table("market_link_changes")
