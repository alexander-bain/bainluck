"""Add futures markets, outcomes, and odds snapshots tables

Revision ID: add_futures_tables
Revises: add_gei_fields
Create Date: 2026-02-02

Adds tables for tracking futures/outrights markets from multiple sources
(The Odds API, Kalshi, etc.) with support for N-way outcomes.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_futures_tables'
down_revision = 'add_gei_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create futures_markets table
    op.create_table(
        'futures_markets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('external_id', sa.String(200), nullable=False),
        sa.Column('sport_id', sa.Integer(), sa.ForeignKey('sports.id'), nullable=True),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), server_default='championship'),
        sa.Column('mutually_exclusive', sa.Boolean(), server_default='true'),
        sa.Column('resolution_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('source', 'external_id', name='uq_futures_source_external'),
    )

    # Index for querying by sport and status
    op.create_index('ix_futures_markets_sport_id', 'futures_markets', ['sport_id'])
    op.create_index('ix_futures_markets_status', 'futures_markets', ['status'])

    # Create futures_outcomes table
    op.create_table(
        'futures_outcomes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(), sa.ForeignKey('futures_markets.id'), nullable=False),
        sa.Column('external_id', sa.String(200), nullable=False),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=True),
        # Current consensus odds
        sa.Column('current_probability', sa.Numeric(7, 6), nullable=True),
        sa.Column('current_american_odds', sa.Integer(), nullable=True),
        # Kalshi-specific bid/ask
        sa.Column('current_yes_bid', sa.Numeric(5, 4), nullable=True),
        sa.Column('current_yes_ask', sa.Numeric(5, 4), nullable=True),
        # Opening odds
        sa.Column('opening_probability', sa.Numeric(7, 6), nullable=True),
        sa.Column('opening_american_odds', sa.Integer(), nullable=True),
        sa.Column('opening_captured_at', sa.DateTime(timezone=True), nullable=True),
        # Movement tracking
        sa.Column('probability_change_24h', sa.Numeric(7, 6), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('rank_change_24h', sa.Integer(), nullable=True),
        # Resolution
        sa.Column('is_winner', sa.Boolean(), server_default='false'),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('market_id', 'external_id', name='uq_outcome_market_external'),
    )

    op.create_index('ix_futures_outcomes_market_id', 'futures_outcomes', ['market_id'])
    op.create_index('ix_futures_outcomes_rank', 'futures_outcomes', ['rank'])

    # Create futures_odds_snapshots table
    op.create_table(
        'futures_odds_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('outcome_id', sa.Integer(), sa.ForeignKey('futures_outcomes.id'), nullable=False),
        sa.Column('bookmaker', sa.String(50), nullable=False),
        sa.Column('probability', sa.Numeric(7, 6), nullable=False),
        # Source-specific raw data
        sa.Column('american_odds', sa.Integer(), nullable=True),
        sa.Column('yes_bid', sa.Numeric(5, 4), nullable=True),
        sa.Column('yes_ask', sa.Numeric(5, 4), nullable=True),
        sa.Column('last_price', sa.Numeric(5, 4), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Deduplication
        sa.Column('reading_count', sa.Integer(), server_default='1'),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('ix_futures_odds_snapshots_outcome_id', 'futures_odds_snapshots', ['outcome_id'])
    op.create_index('ix_futures_odds_snapshots_captured_at', 'futures_odds_snapshots', ['captured_at'])


def downgrade() -> None:
    op.drop_index('ix_futures_odds_snapshots_captured_at', table_name='futures_odds_snapshots')
    op.drop_index('ix_futures_odds_snapshots_outcome_id', table_name='futures_odds_snapshots')
    op.drop_table('futures_odds_snapshots')

    op.drop_index('ix_futures_outcomes_rank', table_name='futures_outcomes')
    op.drop_index('ix_futures_outcomes_market_id', table_name='futures_outcomes')
    op.drop_table('futures_outcomes')

    op.drop_index('ix_futures_markets_status', table_name='futures_markets')
    op.drop_index('ix_futures_markets_sport_id', table_name='futures_markets')
    op.drop_table('futures_markets')
