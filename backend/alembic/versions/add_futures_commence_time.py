"""Add commence_time column to futures_markets

Revision ID: add_futures_commence_time
Revises: add_futures_search_index
Create Date: 2026-02-03

Adds commence_time field to track when the event/tournament begins,
separate from resolution_date which tracks when the market resolves.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_futures_commence_time'
down_revision = 'add_futures_search_index'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'futures_markets',
        sa.Column('commence_time', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('futures_markets', 'commence_time')
