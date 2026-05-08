"""Add Discover feed query indexes.

Revision ID: add_discover_feed_indexes
Revises: merge_hooks_bugs
Create Date: 2026-05-08
"""

from alembic import op


revision = "add_discover_feed_indexes"
down_revision = "merge_hooks_bugs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_feed_open_sports
        ON futures_markets (llm_sport_category, market_tier, resolution_date)
        WHERE status = 'open' AND event_id IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_feed_open_volume
        ON futures_markets (volume_24h DESC NULLS LAST, market_tier)
        WHERE status = 'open' AND event_id IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_feed_open_enriched
        ON futures_markets (hook_generated_at DESC NULLS LAST, updated_at DESC NULLS LAST)
        WHERE status = 'open'
          AND event_id IS NULL
          AND (hook_description IS NOT NULL OR image_url IS NOT NULL)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_feed_open_timely
        ON futures_markets (resolution_date, volume_24h DESC NULLS LAST)
        WHERE status = 'open' AND event_id IS NULL AND resolution_date IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_canonical_source_count
        ON futures_markets (canonical_market_key, source)
        WHERE canonical_market_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fo_market_movement
        ON futures_outcomes (market_id, probability_change_24h)
        WHERE probability_change_24h IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_fo_market_movement", table_name="futures_outcomes", if_exists=True)
    op.drop_index("ix_fm_canonical_source_count", table_name="futures_markets", if_exists=True)
    op.drop_index("ix_fm_feed_open_timely", table_name="futures_markets", if_exists=True)
    op.drop_index("ix_fm_feed_open_enriched", table_name="futures_markets", if_exists=True)
    op.drop_index("ix_fm_feed_open_volume", table_name="futures_markets", if_exists=True)
    op.drop_index("ix_fm_feed_open_sports", table_name="futures_markets", if_exists=True)
