"""add_bookmaker_closing_line_index

Revision ID: 4623658a2704
Revises: add_max_movement_24h
Create Date: 2026-05-21 15:47:33.414083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4623658a2704'
down_revision: Union[str, None] = 'add_max_movement_24h'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_odds_snapshots_bookmaker_closing "
        "ON odds_snapshots (event_id, bookmaker, captured_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_odds_snapshots_bookmaker_closing", "odds_snapshots")
