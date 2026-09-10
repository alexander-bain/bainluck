"""Stamp live scores with when they were observed and by whom (#4571)

Adds ``events.score_source`` and ``events.score_observed_at``.

Both nullable with no server default, and deliberately so: a backfill would be
an invention. We do not know when any score already in the table was observed,
and writing ``now()`` across them would assert that every historical score was
read at migration time — the precise lie the columns exist to remove. NULL
reads as "unknown age", which is the truth for every pre-#4571 row. Live rows
acquire a stamp on the next pass of their writer (30s StatPal / 60s ESPN), so
the population that matters self-heals within a minute of deploy.

No index: the columns are read per-row on a payload the row is already loaded
for, and the attribution query behind #4576 is bounded by
``score_snapshots.event_id`` (already indexed), not by these.

Revision ID: score_observation_stamp
Revises: containers_phase1
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic. (<=32 chars — gotcha #1)
revision = "score_observation_stamp"
down_revision = "containers_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("score_source", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column(
            "score_observed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("events", "score_observed_at")
    op.drop_column("events", "score_source")
