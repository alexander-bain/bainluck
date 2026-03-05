"""Add group_id, group_type, group_position to futures_markets.

Revision ID: add_fm_group_cols
Revises: rename_fg_to_mlb
Create Date: 2026-03-05
"""

# revision identifiers
revision = "add_fm_group_cols"
down_revision = "rename_fg_to_mlb"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("futures_markets", sa.Column("group_id", sa.String(200), nullable=True))
    op.add_column("futures_markets", sa.Column("group_type", sa.String(50), nullable=True))
    op.add_column("futures_markets", sa.Column("group_position", sa.Integer(), nullable=True))
    op.create_index("ix_futures_markets_group_id", "futures_markets", ["group_id"])


def downgrade():
    op.drop_index("ix_futures_markets_group_id", table_name="futures_markets")
    op.drop_column("futures_markets", "group_position")
    op.drop_column("futures_markets", "group_type")
    op.drop_column("futures_markets", "group_id")
