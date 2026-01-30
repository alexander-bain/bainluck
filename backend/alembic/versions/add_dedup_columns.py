"""Add deduplication columns to odds_snapshots

Revision ID: add_dedup_columns
Revises: d4029b6f1add
Create Date: 2026-01-30

Adds reading_count and valid_until columns to support duplicate detection.
Instead of storing identical rows, we increment reading_count and update valid_until.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_dedup_columns'
down_revision = 'd4029b6f1add'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add reading_count with default 1 (existing rows have been read once)
    op.add_column('odds_snapshots',
        sa.Column('reading_count', sa.Integer(), nullable=False, server_default='1')
    )

    # Add valid_until (nullable - will be set when we see next different value)
    op.add_column('odds_snapshots',
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True)
    )

    # Add index for efficient "latest snapshot" queries
    op.create_index(
        'ix_odds_snapshots_event_bookmaker_captured',
        'odds_snapshots',
        ['event_id', 'bookmaker', 'captured_at'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_odds_snapshots_event_bookmaker_captured', table_name='odds_snapshots')
    op.drop_column('odds_snapshots', 'valid_until')
    op.drop_column('odds_snapshots', 'reading_count')
