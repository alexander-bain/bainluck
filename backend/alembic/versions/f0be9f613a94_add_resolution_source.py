"""add_resolution_source

Revision ID: f0be9f613a94
Revises: 4623658a2704
Create Date: 2026-05-21 16:23:45.997886

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0be9f613a94'
down_revision: Union[str, None] = '4623658a2704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "futures_outcomes",
        sa.Column("resolution_source", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("futures_outcomes", "resolution_source")
