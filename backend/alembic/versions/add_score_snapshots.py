"""Add score_snapshots table for score history tracking

Revision ID: add_score_snapshots
Revises: add_dedup_columns
Create Date: 2026-01-31

Adds score_snapshots table to track score changes over time for live games.
This enables the Score Progression chart on the event detail page.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_score_snapshots'
down_revision = 'add_dedup_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'score_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('events.id'), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('home_score', sa.Integer(), nullable=False),
        sa.Column('away_score', sa.Integer(), nullable=False),
    )

    # Add indexes for efficient queries
    op.create_index('ix_score_snapshots_event_id', 'score_snapshots', ['event_id'])
    op.create_index('ix_score_snapshots_captured_at', 'score_snapshots', ['captured_at'])


def downgrade() -> None:
    op.drop_index('ix_score_snapshots_captured_at', table_name='score_snapshots')
    op.drop_index('ix_score_snapshots_event_id', table_name='score_snapshots')
    op.drop_table('score_snapshots')
