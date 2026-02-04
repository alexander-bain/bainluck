"""Increase period column size for ESPN status details

Revision ID: increase_period_size
Revises: add_team_name_normalization
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'increase_period_size'
down_revision: Union[str, None] = 'add_team_name_normalization'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ESPN returns longer status details like "Wed, February 4th at 9:30 PM EST"
    # Increase from VARCHAR(20) to VARCHAR(100)
    op.alter_column('events', 'period',
                    type_=sa.String(100),
                    existing_type=sa.String(20),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('events', 'period',
                    type_=sa.String(20),
                    existing_type=sa.String(100),
                    existing_nullable=True)
