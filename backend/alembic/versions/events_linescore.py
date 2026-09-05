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

PARENT RE-POINTED 2026-09-05 (live/062 repair, integrator/207 finding). This
revision was cut against `link_change_history`, but `uq_event_espn_id` landed on
master afterwards declaring that same parent. Both would have been heads the
moment this chain merged: the heads/orphans CI gate fails, and past it the
Heroku release phase aborts on multiple head revisions and the web dyno does not
come back (gotchas #1/#8). The column itself is unchanged — this is a graph
re-point only, chosen over a merge revision because the column has no dependants
and a single parent keeps the line linear.

Revision ID: events_linescore
Revises: uq_event_espn_id
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "events_linescore"
down_revision = "uq_event_espn_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("linescore", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "linescore")
