"""Add trigram indexes for team name search

Revision ID: add_search_indexes
Revises: add_gei_fields
Create Date: 2026-02-02

Adds pg_trgm extension and trigram indexes on home_team_name and
away_team_name columns to optimize ILIKE searches.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_search_indexes'
down_revision = 'add_gei_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pg_trgm extension for trigram similarity search
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # Create trigram indexes for fast ILIKE searches on team names
    op.execute('''
        CREATE INDEX IF NOT EXISTS ix_events_home_team_name_trgm
        ON events USING gin (home_team_name gin_trgm_ops)
    ''')
    op.execute('''
        CREATE INDEX IF NOT EXISTS ix_events_away_team_name_trgm
        ON events USING gin (away_team_name gin_trgm_ops)
    ''')

    # Also add a standard index on commence_time + status for efficient filtering
    op.create_index(
        'ix_events_commence_status',
        'events',
        ['commence_time', 'status'],
        if_not_exists=True
    )


def downgrade() -> None:
    op.drop_index('ix_events_commence_status', table_name='events')
    op.execute('DROP INDEX IF EXISTS ix_events_away_team_name_trgm')
    op.execute('DROP INDEX IF EXISTS ix_events_home_team_name_trgm')
    # Note: We don't drop the pg_trgm extension as other things may depend on it
