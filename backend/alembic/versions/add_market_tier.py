"""Add market_tier column to futures_markets for relevance ranking.

Tier values: 1=championship, 2=conference, 3=awards/mvp, 4=division, 5=props/other.
Used to rank related futures on event detail pages.

Revision ID: add_market_tier
Revises: add_winprob_dedup_cols
Create Date: 2026-02-10
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_market_tier'
down_revision: Union[str, None] = 'add_winprob_dedup_cols'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('futures_markets',
        sa.Column('market_tier', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('futures_markets', 'market_tier')
