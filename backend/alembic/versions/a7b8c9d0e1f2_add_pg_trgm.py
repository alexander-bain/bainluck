"""Enable pg_trgm and add GIN trigram indexes for fuzzy search

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-05-02

"""
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_teams_name_trgm "
        "ON teams USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_events_home_trgm "
        "ON events USING gin (home_team_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_events_away_trgm "
        "ON events USING gin (away_team_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_futures_name_trgm "
        "ON futures_markets USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_futures_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_events_away_trgm")
    op.execute("DROP INDEX IF EXISTS ix_events_home_trgm")
    op.execute("DROP INDEX IF EXISTS ix_teams_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
