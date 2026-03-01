"""Add market_tags JSONB column with GIN index to futures_markets table.

Stores deterministic taxonomy tags for futures markets,
e.g. ["category:championship", "source:polymarket", "market_status:open"].
Queryable via GIN containment: WHERE market_tags @> '["category:championship"]'

Revision ID: add_market_tags
Revises: add_event_tags
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = "add_market_tags"
down_revision = "add_event_tags"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "futures_markets",
        sa.Column("market_tags", JSONB, server_default="[]", nullable=True),
    )
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_futures_markets_market_tags "
        "ON futures_markets USING gin (market_tags jsonb_path_ops)"
    )


def downgrade():
    op.drop_index("ix_futures_markets_market_tags", table_name="futures_markets")
    op.drop_column("futures_markets", "market_tags")
