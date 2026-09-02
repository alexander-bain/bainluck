"""Matching receipts: why every market is, or is not, attached to an event.

#2705, step 1 of the durable matching program (#2693). One row per market,
upserted by the matcher on every attempt. The reasoning for the shape is in
``app/utils/match_receipts.py`` and the model docstring; this file is the DDL.

DEPLOY SAFETY. CREATE TABLE on an empty relation plus four indexes over zero
rows is metadata-only and completes in milliseconds — the Heroku release phase's
~5-minute timeout (gotcha #31) is not in play, and no CONCURRENTLY is needed or
permitted here. Nothing reads the table until the matcher's next run, so the
release is safe with it empty and the app is safe if the matcher is rolled back
with the table present.

THE FK CASCADES. A receipt for a deleted market is a dangling answer; the twin
cleanup in step 2 will delete markets, and it must not leave orphan receipts
behind for the reconciliation job to count.

Revision ID: match_receipts
Revises: add_image_dimensions
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "match_receipts"
down_revision = "add_image_dimensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_match_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("market_name", sa.String(length=300), nullable=True),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reject_reason", sa.String(length=40), nullable=True),
        sa.Column("linked_event_id", sa.Integer(), nullable=True),
        sa.Column(
            "candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=True,
        ),
        sa.Column(
            "detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "first_attempted_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "last_attempted_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["market_id"], ["futures_markets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Identity: one receipt per market, and the ON CONFLICT target the writer
    # names. Index names match ``MarketMatchReceipt.__table_args__`` exactly.
    op.create_index(
        "uq_match_receipt_market", "market_match_receipts", ["market_id"], unique=True
    )
    # The coverage metric: max(now() - last_attempted_at) over open unlinked
    # markets, and the backlog pass's ORDER BY.
    op.create_index(
        "ix_match_receipt_last_attempted",
        "market_match_receipts",
        ["last_attempted_at"],
    )
    # Every reconciliation question is a GROUP BY on the reason.
    op.create_index(
        "ix_match_receipt_reason",
        "market_match_receipts",
        ["reject_reason", "source"],
    )
    # "Which markets landed on this event, and why."
    op.create_index(
        "ix_match_receipt_event", "market_match_receipts", ["linked_event_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_match_receipt_event", table_name="market_match_receipts")
    op.drop_index("ix_match_receipt_reason", table_name="market_match_receipts")
    op.drop_index(
        "ix_match_receipt_last_attempted", table_name="market_match_receipts"
    )
    op.drop_index("uq_match_receipt_market", table_name="market_match_receipts")
    op.drop_table("market_match_receipts")
