"""Add ESPN integration fields for teams, venues, and events.

Adds:
- Venue table for arena/stadium information
- Team enrichment: ESPN ID, colors, logos, alternate names
- Event enrichment: ESPN ID, venue, broadcast, game clock, win probability

Revision ID: add_espn_integration
Revises: add_llm_metadata_fields
Create Date: 2026-02-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'add_espn_integration'
down_revision = 'add_llm_metadata_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Create venues table
    op.create_table(
        'venues',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(50), nullable=True),
        sa.Column('country', sa.String(50), nullable=True),
        sa.Column('capacity', sa.Integer, nullable=True),
        sa.Column('espn_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_venues_espn_id', 'venues', ['espn_id'])

    # Add ESPN fields to teams
    op.add_column(
        'teams',
        sa.Column('espn_id', sa.String(50), nullable=True)
    )
    op.add_column(
        'teams',
        sa.Column('primary_color', sa.String(7), nullable=True)  # Hex color e.g. #552583
    )
    op.add_column(
        'teams',
        sa.Column('secondary_color', sa.String(7), nullable=True)
    )
    op.add_column(
        'teams',
        sa.Column('logo_url_small', sa.String(512), nullable=True)
    )
    op.add_column(
        'teams',
        sa.Column('logo_url_large', sa.String(512), nullable=True)
    )
    op.add_column(
        'teams',
        sa.Column('alternate_names', JSONB, nullable=True)  # ["Lakers", "LA Lakers", "Los Angeles"]
    )
    op.add_column(
        'teams',
        sa.Column('current_record', sa.String(20), nullable=True)  # "34-18"
    )
    op.create_index('ix_teams_espn_id', 'teams', ['espn_id'])

    # Add ESPN fields to events
    op.add_column(
        'events',
        sa.Column('espn_id', sa.String(50), nullable=True)
    )
    op.add_column(
        'events',
        sa.Column('venue_id', sa.Integer, sa.ForeignKey('venues.id'), nullable=True)
    )
    op.add_column(
        'events',
        sa.Column('broadcast_info', sa.String(255), nullable=True)  # "ESPN, ESPN+"
    )
    op.add_column(
        'events',
        sa.Column('game_clock', sa.String(20), nullable=True)  # "4:32"
    )
    op.add_column(
        'events',
        sa.Column('period', sa.String(20), nullable=True)  # "Q4", "2nd Half", "OT"
    )
    op.add_column(
        'events',
        sa.Column('espn_win_prob_home', sa.Numeric(5, 4), nullable=True)  # ESPN's statistical model
    )
    op.add_column(
        'events',
        sa.Column('win_probability_sources', JSONB, nullable=True)  # {"espn": 0.65, "betting": 0.60}
    )
    op.create_index('ix_events_espn_id', 'events', ['espn_id'])


def downgrade():
    # Remove event columns
    op.drop_index('ix_events_espn_id', 'events')
    op.drop_column('events', 'win_probability_sources')
    op.drop_column('events', 'espn_win_prob_home')
    op.drop_column('events', 'period')
    op.drop_column('events', 'game_clock')
    op.drop_column('events', 'broadcast_info')
    op.drop_column('events', 'venue_id')
    op.drop_column('events', 'espn_id')

    # Remove team columns
    op.drop_index('ix_teams_espn_id', 'teams')
    op.drop_column('teams', 'current_record')
    op.drop_column('teams', 'alternate_names')
    op.drop_column('teams', 'logo_url_large')
    op.drop_column('teams', 'logo_url_small')
    op.drop_column('teams', 'secondary_color')
    op.drop_column('teams', 'primary_color')
    op.drop_column('teams', 'espn_id')

    # Drop venues table
    op.drop_index('ix_venues_espn_id', 'venues')
    op.drop_table('venues')
