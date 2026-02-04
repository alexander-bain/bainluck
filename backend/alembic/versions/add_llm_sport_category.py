"""Add llm_sport_category column to futures_markets.

Stores LLM-assigned sport category for markets that can't be
categorized by pattern matching rules.

Revision ID: add_llm_sport_category
Revises: add_futures_commence_time
Create Date: 2026-02-04
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_llm_sport_category'
down_revision = 'add_futures_commence_time'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'futures_markets',
        sa.Column('llm_sport_category', sa.String(50), nullable=True)
    )


def downgrade():
    op.drop_column('futures_markets', 'llm_sport_category')
