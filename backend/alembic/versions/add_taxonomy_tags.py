"""Add event_tags and market_tags JSONB columns with GIN indexes.

event_tags on events table — namespaced taxonomy tags for events.
market_tags on futures_markets table — namespaced taxonomy tags for futures.

Uses CREATE INDEX CONCURRENTLY to avoid blocking writes during migration.

Revision ID: add_taxonomy_tags
Revises: add_box_score_data
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = "add_taxonomy_tags"
down_revision = "add_box_score_data"
branch_labels = None
depends_on = None


def upgrade():
    # Add columns
    op.add_column("events", sa.Column("event_tags", JSONB, server_default="[]", nullable=True))
    op.add_column("futures_markets", sa.Column("market_tags", JSONB, server_default="[]", nullable=True))

    # GIN indexes for fast containment queries (@>)
    # Using raw SQL with CONCURRENTLY to avoid SHARE lock that blocks worker writes.
    # Note: CONCURRENTLY requires the migration to NOT run inside a transaction.
    op.execute("COMMIT")  # End the implicit transaction so CONCURRENTLY works
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_event_tags "
        "ON events USING gin (event_tags jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_futures_markets_market_tags "
        "ON futures_markets USING gin (market_tags jsonb_path_ops)"
    )


def downgrade():
    op.drop_index("ix_futures_markets_market_tags", table_name="futures_markets")
    op.drop_index("ix_events_event_tags", table_name="events")
    op.drop_column("futures_markets", "market_tags")
    op.drop_column("events", "event_tags")
