"""Add generic win_prob_snapshots table for multi-source win probabilities.

Revision ID: add_win_prob_snapshots
Revises: add_outcome_name_search_idx
Create Date: 2026-02-08
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'add_win_prob_snapshots'
down_revision: Union[str, None] = 'add_outcome_name_search_idx'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        'win_prob_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(30), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('home_win_probability', sa.Numeric(5, 4), nullable=True),
        sa.Column('away_win_probability', sa.Numeric(5, 4), nullable=True),
        sa.Column('draw_probability', sa.Numeric(5, 4), nullable=True),
        sa.Column('game_state', JSONB, nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_winprob_event_source', 'win_prob_snapshots', ['event_id', 'source'])
    op.create_index('ix_winprob_captured', 'win_prob_snapshots', ['captured_at'])


def downgrade() -> None:
    op.drop_index('ix_winprob_captured', table_name='win_prob_snapshots')
    op.drop_index('ix_winprob_event_source', table_name='win_prob_snapshots')
    op.drop_table('win_prob_snapshots')
