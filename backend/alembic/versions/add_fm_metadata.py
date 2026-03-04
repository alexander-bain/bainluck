"""Add metadata JSONB column to futures_markets.

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
    op.add_column("futures_markets", sa.Column("metadata", JSONB, nullable=True))


def downgrade():
    op.drop_column("futures_markets", "metadata")
