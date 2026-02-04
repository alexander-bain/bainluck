"""Add ESPN snapshots table for win probability history

Revision ID: add_espn_snapshots
Revises: increase_period_size
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_espn_snapshots'
down_revision: Union[str, None] = 'increase_period_size'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'espn_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('home_win_probability', sa.Numeric(5, 4), nullable=True),
        sa.Column('away_win_probability', sa.Numeric(5, 4), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('game_clock', sa.String(20), nullable=True),
        sa.Column('period', sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    # Index for fast lookups by event
    op.create_index('ix_espn_snapshots_event_id', 'espn_snapshots', ['event_id'])
    # Index for time-based queries
    op.create_index('ix_espn_snapshots_captured_at', 'espn_snapshots', ['captured_at'])
    # Composite index for event + time queries
    op.create_index('ix_espn_snapshots_event_time', 'espn_snapshots', ['event_id', 'captured_at'])


def downgrade() -> None:
    op.drop_index('ix_espn_snapshots_event_time', table_name='espn_snapshots')
    op.drop_index('ix_espn_snapshots_captured_at', table_name='espn_snapshots')
    op.drop_index('ix_espn_snapshots_event_id', table_name='espn_snapshots')
    op.drop_table('espn_snapshots')
