"""#12818: add three open-market partial indexes on futures_markets.

MIGRATION-CLASS (D45 / notice 47b): merged and applied only on Alex's separate
go. Prepared ahead of Step 1 open-catalog growth (55k -> 179.2k open markets):

1. ``ix_fm_open_volume_24h``:
   Covers open markets sorted by 24h volume (``enrich_cu_v2_profiles`` Phase 1
   and open catalog volume scans across all open markets, including
   event-linked ones that ``ix_fm_feed_open_volume`` omits).
2. ``ix_fm_open_resolution_date``:
   Covers open markets with a ``resolution_date`` (e.g. ``daily_digest``,
   open expiry windows, and resolution-date scans across all open markets).
3. ``ix_fm_open_pm_event_slug``:
   Prefix-capable (``text_pattern_ops``) partial expression index on
   ``market_metadata ->> 'polymarket_event_slug'`` for open markets, serving
   ``_verified_title_candidates_stmt``'s ``slug LIKE :stem || '%'`` lookup.

THE UNDO LINE (D51):

    alembic downgrade retired_team_redirects_13229

Deploy safety:
Fully transactional single-unit migration (preserves ``env.py`` lock-timeout
retry under ``app.utils.migration_lock_budget``), and no ``CONCURRENTLY`` inside
``upgrade()`` (gotcha #31 / ``test_futures_stamp_semantics.py``). Because
``CREATE INDEX IF NOT EXISTS`` is used, an operator may optionally pre-build
these CONCURRENTLY via ``psql`` ahead of the release if desired, making release
application a metadata no-op:

    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fm_open_volume_24h
        ON futures_markets (volume_24h DESC NULLS LAST, updated_at DESC NULLS LAST, id)
        WHERE status = 'open';
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fm_open_resolution_date
        ON futures_markets (resolution_date ASC, volume_24h DESC NULLS LAST, id)
        WHERE status = 'open' AND resolution_date IS NOT NULL;
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fm_open_pm_event_slug
        ON futures_markets ((market_metadata ->> 'polymarket_event_slug') text_pattern_ops)
        WHERE status = 'open' AND (market_metadata ->> 'polymarket_event_slug') IS NOT NULL;

Revision ID: fm_open_indexes_12818
Revises: retired_team_redirects_13229
"""

from typing import Sequence, Union

from alembic import op

revision: str = "fm_open_indexes_12818"
down_revision: Union[str, None] = "retired_team_redirects_13229"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_open_volume_24h
        ON futures_markets (volume_24h DESC NULLS LAST, updated_at DESC NULLS LAST, id)
        WHERE status = 'open'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_open_resolution_date
        ON futures_markets (resolution_date ASC, volume_24h DESC NULLS LAST, id)
        WHERE status = 'open' AND resolution_date IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fm_open_pm_event_slug
        ON futures_markets ((market_metadata ->> 'polymarket_event_slug') text_pattern_ops)
        WHERE status = 'open' AND (market_metadata ->> 'polymarket_event_slug') IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fm_open_pm_event_slug", table_name="futures_markets", if_exists=True
    )
    op.drop_index(
        "ix_fm_open_resolution_date", table_name="futures_markets", if_exists=True
    )
    op.drop_index(
        "ix_fm_open_volume_24h", table_name="futures_markets", if_exists=True
    )
