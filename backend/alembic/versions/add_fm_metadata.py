"""Add market_metadata JSONB column to futures_markets.

Revision ID: add_fm_metadata
Revises: add_market_tags
Create Date: 2026-03-03
"""

# revision identifiers
revision = "add_fm_metadata"
down_revision = "add_market_tags"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    conn = op.get_bind()
    # Check if either column name already exists (handles re-run scenarios)
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'futures_markets' "
            "AND column_name IN ('metadata', 'market_metadata')"
        )
    )
    existing = {row[0] for row in result.fetchall()}
    if "market_metadata" not in existing and "metadata" not in existing:
        op.add_column("futures_markets", sa.Column("market_metadata", JSONB, nullable=True))


def downgrade():
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'futures_markets' AND column_name = 'market_metadata'"
        )
    )
    if result.fetchone():
        op.drop_column("futures_markets", "market_metadata")
