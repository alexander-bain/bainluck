"""Add LLM metadata enrichment fields to events and futures_markets.

Adds columns for:
- llm_gender: men/women/mixed/unknown
- llm_level: professional/college/amateur/youth
- llm_league: More granular than sport (NFL, NCAAF, NBA, etc.)
- llm_importance: playoff/championship/regular_season/exhibition/preseason

These enable filtering and better categorization of events.

Revision ID: add_llm_metadata_fields
Revises: add_llm_sport_category
Create Date: 2026-02-04
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_llm_metadata_fields'
down_revision = 'add_llm_sport_category'
branch_labels = None
depends_on = None


def upgrade():
    # Add LLM metadata columns to events
    op.add_column(
        'events',
        sa.Column('llm_gender', sa.String(20), nullable=True)
    )
    op.add_column(
        'events',
        sa.Column('llm_level', sa.String(20), nullable=True)
    )
    op.add_column(
        'events',
        sa.Column('llm_league', sa.String(50), nullable=True)
    )
    op.add_column(
        'events',
        sa.Column('llm_importance', sa.String(30), nullable=True)
    )

    # Add LLM metadata columns to futures_markets
    op.add_column(
        'futures_markets',
        sa.Column('llm_gender', sa.String(20), nullable=True)
    )
    op.add_column(
        'futures_markets',
        sa.Column('llm_level', sa.String(20), nullable=True)
    )
    op.add_column(
        'futures_markets',
        sa.Column('llm_league', sa.String(50), nullable=True)
    )


def downgrade():
    # Remove from futures_markets
    op.drop_column('futures_markets', 'llm_league')
    op.drop_column('futures_markets', 'llm_level')
    op.drop_column('futures_markets', 'llm_gender')

    # Remove from events
    op.drop_column('events', 'llm_importance')
    op.drop_column('events', 'llm_league')
    op.drop_column('events', 'llm_level')
    op.drop_column('events', 'llm_gender')
