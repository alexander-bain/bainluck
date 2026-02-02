"""Add Game Excitement Index fields and percentiles table

Revision ID: add_gei_fields
Revises: add_score_snapshots
Create Date: 2026-02-02

Adds GEI (Game Excitement Index) fields to events table and creates
the gei_percentiles table for storing percentile thresholds.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_gei_fields'
down_revision = 'add_score_snapshots'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add GEI columns to events table
    op.add_column('events',
        sa.Column('raw_gei', sa.Numeric(6, 4), nullable=True)
    )
    op.add_column('events',
        sa.Column('gei_components', sa.Text(), nullable=True)
    )
    op.add_column('events',
        sa.Column('gei_computed_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create gei_percentiles table
    op.create_table(
        'gei_percentiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('scope', sa.String(50), nullable=False),
        sa.Column('percentile', sa.Integer(), nullable=False),
        sa.Column('raw_gei_threshold', sa.Numeric(6, 4), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('scope', 'percentile', name='uq_scope_percentile'),
    )

    # Add index for efficient percentile lookups
    op.create_index('ix_gei_percentiles_scope', 'gei_percentiles', ['scope'])

    # Add index for finding events with GEI
    op.create_index('ix_events_raw_gei', 'events', ['raw_gei'])


def downgrade() -> None:
    op.drop_index('ix_events_raw_gei', table_name='events')
    op.drop_index('ix_gei_percentiles_scope', table_name='gei_percentiles')
    op.drop_table('gei_percentiles')
    op.drop_column('events', 'gei_computed_at')
    op.drop_column('events', 'gei_components')
    op.drop_column('events', 'raw_gei')
