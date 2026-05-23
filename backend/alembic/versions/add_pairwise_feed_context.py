"""add feed context to pairwise labels

Revision ID: e5f6a7b8c9d0
Revises: bd72c1098b88
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "bd72c1098b88"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("discover_pairwise_labels", sa.Column("pair_id", sa.String(100), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("pair_strategy", sa.String(80), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("surface", sa.String(50), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("batch_id", sa.String(100), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("confidence", sa.String(20), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("ranking_error", sa.Boolean(), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("card_a_snapshot", JSONB, nullable=True))
    op.add_column("discover_pairwise_labels", sa.Column("card_b_snapshot", JSONB, nullable=True))
    op.create_index("ix_discover_pairwise_labels_pair_id", "discover_pairwise_labels", ["pair_id"])


def downgrade() -> None:
    op.drop_index("ix_discover_pairwise_labels_pair_id", table_name="discover_pairwise_labels")
    op.drop_column("discover_pairwise_labels", "card_b_snapshot")
    op.drop_column("discover_pairwise_labels", "card_a_snapshot")
    op.drop_column("discover_pairwise_labels", "notes")
    op.drop_column("discover_pairwise_labels", "ranking_error")
    op.drop_column("discover_pairwise_labels", "confidence")
    op.drop_column("discover_pairwise_labels", "batch_id")
    op.drop_column("discover_pairwise_labels", "surface")
    op.drop_column("discover_pairwise_labels", "pair_strategy")
    op.drop_column("discover_pairwise_labels", "pair_id")
