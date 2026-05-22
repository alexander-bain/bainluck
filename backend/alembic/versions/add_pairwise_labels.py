"""add discover_pairwise_labels table

Revision ID: a1b2c3d4e5f6
Revises: c3f8a1b2d4e5
Create Date: 2026-05-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c3f8a1b2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discover_pairwise_labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reviewer", sa.String(100), nullable=False),
        sa.Column(
            "card_a_market_id",
            sa.Integer(),
            sa.ForeignKey("futures_markets.id"),
            nullable=False,
        ),
        sa.Column(
            "card_b_market_id",
            sa.Integer(),
            sa.ForeignKey("futures_markets.id"),
            nullable=False,
        ),
        sa.Column("card_a_score", sa.Float(), nullable=True),
        sa.Column("card_b_score", sa.Float(), nullable=True),
        sa.Column("choice", sa.String(10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("discover_pairwise_labels")
