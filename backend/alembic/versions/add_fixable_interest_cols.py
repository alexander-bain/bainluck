"""add fixable interest fields to ranking judgments

Revision ID: a3b4c5d6e7f8
Revises: e5f6a7b8c9d0
Create Date: 2026-05-25
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "ranking_judgments",
        sa.Column("fixable_interesting", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "ranking_judgments",
        sa.Column("repair_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "ranking_judgments",
        sa.Column("repair_target_entity", sa.Text(), nullable=True),
    )
    op.add_column(
        "ranking_judgments",
        sa.Column("repair_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ranking_judgments", "repair_note")
    op.drop_column("ranking_judgments", "repair_target_entity")
    op.drop_column("ranking_judgments", "repair_type")
    op.drop_column("ranking_judgments", "fixable_interesting")
