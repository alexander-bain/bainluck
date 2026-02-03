"""Add trigram index for futures market name search

Revision ID: add_futures_search_index
Revises: add_search_indexes
Create Date: 2026-02-03

Adds trigram index on futures_markets.name to enable fast ILIKE searches
for futures markets alongside regular events.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'add_futures_search_index'
down_revision = 'add_search_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trigram index for fast ILIKE searches on futures market names
    # pg_trgm extension already enabled by add_search_indexes migration
    op.execute('''
        CREATE INDEX IF NOT EXISTS ix_futures_markets_name_trgm
        ON futures_markets USING gin (name gin_trgm_ops)
    ''')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_futures_markets_name_trgm')
