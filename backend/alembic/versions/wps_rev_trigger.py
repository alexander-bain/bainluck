"""#9051: `events.win_probability_sources_rev` and the trigger that bumps it. ADDITIVE ONLY.

THE SHIP. A removed source stops influencing the held headline and chart, and
valid survivor quotes and re-admissions still land.

WHY A COLUMN, and why no existing one will do. The page holds a FOLDED blend
(the canonical row's sources plus what its tagged twins add), and a client
handed a second fold must know whether it is newer. Quote clocks cannot say:
a survivor observed before a removal can commit after it, and a twin's removal
can commit after the canonical's while carrying the earlier stamp (Codex,
twin-contract/CONTRACT-REVIEW.md, on the actual fold helpers). What orders two
reads of a row is the order its writes COMMITTED, and only the database sees
that. `xmin` was the one candidate already on the row. It is assigned when a
transaction takes its xid, not when it commits, so it is not monotonic per row.
It also wraps at 2^32 and moves on every column's update. Hence a counter.

WHAT THIS DOES, EXHAUSTIVELY:

* Adds `events.win_probability_sources_rev bigint NOT NULL DEFAULT 0`. A
  constant default is catalog-only in PostgreSQL 11+: no table rewrite, no
  backfill scan. Every existing row reads 0.
* Creates the plpgsql function `bump_win_probability_sources_rev()`, which sets
  `NEW.rev = OLD.rev + 1`.
* Creates the `BEFORE UPDATE ... FOR EACH ROW` trigger on `events`, with
  `WHEN (OLD.win_probability_sources IS DISTINCT FROM NEW.win_probability_sources)`.
  The row lock serializes writers of one row, and the second writer's UPDATE
  re-reads the first writer's committed row before the trigger runs. So
  `OLD.rev + 1` is commit order for that row, and it covers every writer.

Nothing is dropped. No existing column changes. No data is written. No index is
created (gotcha #31 does not apply).

LOCKS. `ADD COLUMN` and `CREATE TRIGGER` each take a brief lock on `events`.
Neither scans the table. `alembic/env.py` already sets the connection's
`lock_timeout` and wraps the batch in `run_with_lock_retry`, so a long-running
`events` writer makes this retry rather than queue the site behind it.

The statements live in `app/utils/wps_revision.py`, which the model's
`after_create` hook also runs, so every real-Postgres gate carries this exact
trigger.

MIGRATION-CLASS (D45 / notice 47b): merged only on Alex's word, and no default
fires on silence.

Reversible. The D51 undo line, which drops exactly what this adds:

    alembic downgrade fo_volume_24h

Revision ID: wps_rev_trigger
Revises: fo_volume_24h
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa

from app.utils.wps_revision import (
    CREATE_FUNCTION_SQL,
    CREATE_TRIGGER_SQL,
    DROP_FUNCTION_SQL,
    DROP_TRIGGER_SQL,
    REV_COLUMN,
)

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "wps_rev_trigger"
down_revision = "fo_volume_24h"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            REV_COLUMN, sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.execute(CREATE_FUNCTION_SQL)
    op.execute(DROP_TRIGGER_SQL)
    op.execute(CREATE_TRIGGER_SQL)


def downgrade() -> None:
    op.execute(DROP_TRIGGER_SQL)
    op.execute(DROP_FUNCTION_SQL)
    op.drop_column("events", REV_COLUMN)
