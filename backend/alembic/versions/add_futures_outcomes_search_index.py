"""Add trigram index for futures outcome name search

Revision ID: add_futures_outcomes_search_index
Revises: add_llm_metadata_fields
Create Date: 2026-02-04

Adds trigram index on futures_outcomes.name to enable fast ILIKE searches
that match futures markets by their outcome/label names (e.g., searching
"Sox" finds markets containing "Boston Red Sox" as an outcome).
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'add_futures_outcomes_search_index'
down_revision = 'add_llm_metadata_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trigram index for fast ILIKE searches on futures outcome names
    # pg_trgm extension already enabled by add_search_indexes migration
    op.execute('''
        CREATE INDEX IF NOT EXISTS ix_futures_outcomes_name_trgm
        ON futures_outcomes USING gin (name gin_trgm_ops)
    ''')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_futures_outcomes_name_trgm')
