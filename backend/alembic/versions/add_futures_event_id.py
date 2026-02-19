"""Add event_id FK to futures_markets for game-level market linking.

Revision ID: add_futures_event_id
Revises: add_category_tags
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "add_futures_event_id"
down_revision = "add_category_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_markets",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("events.id"), nullable=True),
    )
    op.create_index(
        "ix_futures_markets_event_id",
        "futures_markets",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_futures_markets_event_id", table_name="futures_markets")
    op.drop_column("futures_markets", "event_id")
