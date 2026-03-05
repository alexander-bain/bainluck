"""Add market_type column to futures_markets.

Revision ID: add_fm_market_type
Revises: add_fm_group_cols
Create Date: 2026-03-05
"""

# revision identifiers
revision = "add_fm_market_type"
down_revision = "add_fm_group_cols"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("futures_markets", sa.Column("market_type", sa.String(30), nullable=True))


def downgrade():
    op.drop_column("futures_markets", "market_type")
