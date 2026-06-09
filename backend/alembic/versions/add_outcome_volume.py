"""Add volume column to futures_outcomes.

Per-outcome trading volume from Kalshi settled events API.
NULL = not yet fetched, 0 = confirmed zero contracts traded.

Revision ID: e8f9a0b1c2d3
Revises: d6e7f8a9b0c1
"""

from alembic import op
import sqlalchemy as sa

revision = "e8f9a0b1c2d3"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_outcomes",
        sa.Column("volume", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_outcomes", "volume")
