"""Rename futures_markets.metadata to market_metadata.

The first deploy created column 'metadata' but SQLAlchemy rejected it
as a reserved attribute name. The model was fixed to use 'market_metadata'
but the DB column was never renamed. This migration fixes the mismatch.

Revision ID: rename_fm_metadata
Revises: add_fm_metadata
Create Date: 2026-03-03
"""

# revision identifiers
revision = "rename_fm_metadata"
down_revision = "add_fm_metadata"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Rename the column if the old name exists
    # Use raw SQL to handle the case where the column might already be named correctly
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'futures_markets' AND column_name = 'metadata'"
        )
    )
    if result.fetchone():
        op.alter_column("futures_markets", "metadata", new_column_name="market_metadata")


def downgrade():
    op.alter_column("futures_markets", "market_metadata", new_column_name="metadata")
