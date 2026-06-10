"""Add story_key column to futures_markets.

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = "c852a0story01"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "futures_markets",
        sa.Column("story_key", sa.String(300), nullable=True),
    )
    op.create_index(
        "ix_futures_markets_story_key",
        "futures_markets",
        ["story_key"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_futures_markets_story_key", table_name="futures_markets")
    op.drop_column("futures_markets", "story_key")
