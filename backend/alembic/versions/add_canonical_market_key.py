"""Add canonical_market_key column and index to futures_markets.

Revision ID: add_canonical_mkt_key
Revises: add_auth_personalization
Create Date: 2026-02-19
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_canonical_mkt_key'
down_revision: Union[str, None] = 'add_auth_personalization'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Add canonical_market_key column
    op.add_column(
        'futures_markets',
        sa.Column('canonical_market_key', sa.String(200), nullable=True)
    )
    # Add index for fast grouping/lookup by canonical key
    op.create_index(
        'ix_futures_markets_canonical_market_key',
        'futures_markets',
        ['canonical_market_key'],
    )


def downgrade() -> None:
    op.drop_index('ix_futures_markets_canonical_market_key', table_name='futures_markets')
    op.drop_column('futures_markets', 'canonical_market_key')
