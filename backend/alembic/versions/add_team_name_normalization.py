"""Add normalized team name columns for better matching.

Revision ID: add_team_name_normalization
Revises: add_espn_integration
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'add_team_name_normalization'
down_revision: Union[str, None] = 'add_espn_integration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add normalized/canonical team names (full names like "Los Angeles Lakers")
    op.add_column('events', sa.Column('home_team_normalized', sa.String(200), nullable=True))
    op.add_column('events', sa.Column('away_team_normalized', sa.String(200), nullable=True))

    # Add alternate names array for matching variations
    op.add_column('events', sa.Column('home_team_alt_names', JSONB, nullable=True))
    op.add_column('events', sa.Column('away_team_alt_names', JSONB, nullable=True))

    # Add indexes for search on normalized names
    op.create_index('ix_events_home_team_normalized', 'events', ['home_team_normalized'])
    op.create_index('ix_events_away_team_normalized', 'events', ['away_team_normalized'])


def downgrade() -> None:
    op.drop_index('ix_events_away_team_normalized', table_name='events')
    op.drop_index('ix_events_home_team_normalized', table_name='events')
    op.drop_column('events', 'away_team_alt_names')
    op.drop_column('events', 'home_team_alt_names')
    op.drop_column('events', 'away_team_normalized')
    op.drop_column('events', 'home_team_normalized')
