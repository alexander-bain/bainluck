"""Add reading_count and valid_until to win_prob_snapshots for deduplication.

Revision ID: add_winprob_dedup_cols
Revises: add_win_prob_snapshots
Create Date: 2026-02-10
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_winprob_dedup_cols'
down_revision: Union[str, None] = 'add_win_prob_snapshots'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('win_prob_snapshots',
        sa.Column('reading_count', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('win_prob_snapshots',
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('win_prob_snapshots', 'valid_until')
    op.drop_column('win_prob_snapshots', 'reading_count')
