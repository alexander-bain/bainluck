"""Add category_tags JSONB column to futures_markets.

Revision ID: add_category_tags
Revises: e83a3d18e4ad
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "add_category_tags"
down_revision = "e83a3d18e4ad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_markets",
        sa.Column("category_tags", JSONB, server_default="[]", nullable=True),
    )
    # GIN index for efficient tag-based queries (e.g., WHERE category_tags @> '["trump"]')
    op.create_index(
        "ix_futures_markets_category_tags",
        "futures_markets",
        ["category_tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_futures_markets_category_tags", table_name="futures_markets")
    op.drop_column("futures_markets", "category_tags")
