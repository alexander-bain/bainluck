"""Add volume/liquidity columns to futures_markets.

Store prediction market volume data (Kalshi, Polymarket) for internal
use in feed ranking, grid confidence weighting, and eval context.

Revision ID: add_volume_to_fm
Revises: add_golf_lb_snap
Create Date: 2026-04-14
"""

revision = "add_volume_to_fm"
down_revision = "add_golf_lb_snap"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("futures_markets", sa.Column("volume", sa.Integer(), nullable=True))
    op.add_column("futures_markets", sa.Column("volume_24h", sa.Integer(), nullable=True))
    op.add_column("futures_markets", sa.Column("open_interest", sa.Integer(), nullable=True))
    op.add_column("futures_markets", sa.Column("liquidity", sa.Numeric(14, 2), nullable=True))
    op.add_column("futures_markets", sa.Column("volume_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("futures_markets", "volume_updated_at")
    op.drop_column("futures_markets", "liquidity")
    op.drop_column("futures_markets", "open_interest")
    op.drop_column("futures_markets", "volume_24h")
    op.drop_column("futures_markets", "volume")
