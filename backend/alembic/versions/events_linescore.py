"""The score at a finer grain than the scoreboard's own unit — `events.linescore`.

live/058, #2746. `events.home_score` for tennis counts SETS, so the live card
has no field a GAME can land in: live/057 measured ESPN publishing 78
game-level changes in 45 minutes while our card moved 9 times. This is the
column those 78 changes land in — every published set, its games, its
tiebreak, and which set is in play. Shape: `app/utils/tennis_linescore.py`.

WHY A COLUMN AND NOT A KEY IN `box_score_data`. That column is documented and
used as "ESPN box score data (populated after game completion)" and its readers
expect the `{"players": ...}` wrapper (gotcha #37). A live, pre-completion
score written into it would be a second meaning for one column, and the first
reader to iterate its keys would find it.

DEPLOY SAFETY (gotcha #31). One nullable column, no index, no backfill, no
default — `ALTER TABLE ... ADD COLUMN` with no DEFAULT is a catalog-only change
in PostgreSQL 11+ and does not rewrite the 30k+ tennis rows or the millions of
others. Nothing reads it until the poller writes it.

Revision ID: events_linescore
Revises: link_change_history
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "events_linescore"
down_revision = "link_change_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("linescore", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "linescore")
