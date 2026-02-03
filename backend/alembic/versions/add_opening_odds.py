"""Add opening odds fields to events table

Revision ID: add_opening_odds
Revises: add_score_snapshots
Create Date: 2026-02-01

Adds opening odds fields to track the first odds received for an event.
Used to detect favorite switches, line movement, and other highlight conditions.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_opening_odds'
down_revision = 'add_score_snapshots'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add opening odds columns to events table
    op.add_column('events', sa.Column('opening_home_probability', sa.Numeric(5, 4), nullable=True))
    op.add_column('events', sa.Column('opening_away_probability', sa.Numeric(5, 4), nullable=True))
    op.add_column('events', sa.Column('opening_home_spread', sa.Numeric(4, 1), nullable=True))
    op.add_column('events', sa.Column('opening_over_under', sa.Numeric(5, 1), nullable=True))
    op.add_column('events', sa.Column('opening_favorite', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'opening_favorite')
    op.drop_column('events', 'opening_over_under')
    op.drop_column('events', 'opening_home_spread')
    op.drop_column('events', 'opening_away_probability')
    op.drop_column('events', 'opening_home_probability')
