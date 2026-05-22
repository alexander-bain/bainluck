"""add_opening_source

Revision ID: abfa60dd064c
Revises: f0be9f613a94
Create Date: 2026-05-21 19:59:03.085722

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abfa60dd064c'
down_revision: Union[str, None] = 'f0be9f613a94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "futures_outcomes",
        sa.Column("opening_source", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_outcomes", "opening_source")
