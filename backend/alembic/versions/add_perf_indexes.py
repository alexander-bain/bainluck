"""Add performance indexes for events, futures, teams, and odds_snapshots.

These indexes address missing coverage on columns heavily used in the
critical-path API endpoints (GET /api/events, GET /api/futures).

Revision ID: add_perf_indexes
Revises: add_auth_personalization
Create Date: 2026-02-18
"""
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_perf_indexes"
down_revision: Union[str, None] = "add_auth_personalization"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # === Critical: Event listing filters ===
    # Every GET /api/events filters by status — currently causes full table scan
    op.create_index("ix_events_status", "events", ["status"], if_not_exists=True)
    # JOIN to sports table on every event listing
    op.create_index("ix_events_sport_id", "events", ["sport_id"], if_not_exists=True)
    # Date-range filtering on every event listing
    op.create_index("ix_events_commence_time", "events", ["commence_time"], if_not_exists=True)

    # === High: Odds snapshot window function ===
    # The ranked subquery partitions by (event_id, bookmaker) ORDER BY captured_at DESC.
    # A composite index lets Postgres satisfy this without a full sort.
    op.create_index(
        "ix_odds_snap_evt_bk_time",
        "odds_snapshots",
        ["event_id", "bookmaker", "captured_at"],
        if_not_exists=True,
    )

    # === High: Futures listing filters ===
    op.create_index("ix_futures_markets_status", "futures_markets", ["status"], if_not_exists=True)
    op.create_index("ix_futures_markets_sport_id", "futures_markets", ["sport_id"], if_not_exists=True)
    op.create_index("ix_futures_markets_source", "futures_markets", ["source"], if_not_exists=True)

    # === Medium: Team lookup ===
    # _build_team_lookup uses Team.alternate_names ? 'name' (JSONB containment)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_teams_alt_names ON teams USING gin(alternate_names jsonb_path_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_teams_alt_names", "teams")
    op.drop_index("ix_futures_markets_source", "futures_markets")
    op.drop_index("ix_futures_markets_sport_id", "futures_markets")
    op.drop_index("ix_futures_markets_status", "futures_markets")
    op.drop_index("ix_odds_snap_evt_bk_time", "odds_snapshots")
    op.drop_index("ix_events_commence_time", "events")
    op.drop_index("ix_events_sport_id", "events")
    op.drop_index("ix_events_status", "events")
