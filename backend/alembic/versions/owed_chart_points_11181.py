"""#11181: durable custody of the live chart points a committed stamp owes.

THE SHIP. Rapid live headlines keep every chart point they owe, including the
final quiet change, through a held chart writer and through a worker restart.

WHY A TABLE. A live stamp's chart point is written after the stamp commits, in
its own transaction, so another transaction's lock on ``win_prob_snapshots``
cannot hold the headline (#10090, #11138). The point waits in memory until the
writer gets to it. Memory is bounded, and it empties when the worker restarts,
so a long hold or a restart lost points. The shared Redis is ``allkeys-lru`` and
acknowledges before it persists, so it cannot hold them either (lane1, #11181,
2026-10-17 16:11Z and 16:28Z). Each owed point is now also a row here:

* INSERTed in the stamp's own transaction. A stamp commits only with its row.
* DELETEd in the same savepoint that writes the point. A replay after a crash
  finds the row gone and writes nothing twice.

WHAT THIS DOES, EXHAUSTIVELY. It creates one new, empty table and one b-tree
index on it. It writes no data, alters no existing table and adds no column.
The index is built on an empty table, so gotcha #31 does not apply.

LOCKS. No foreign key, so creating the table takes no lock on ``events`` or on
any other existing table, and no insert into it ever locks an event or chart
row. Nothing scans an existing table.

SIZE. Rows exist only while a chart writer is behind: at most one per live
event per snapshot interval (25 s), and each is deleted when its point is
written. On a 100-event slate a writer held for 10 minutes leaves about 2,400
rows of a few hundred bytes each.

MIGRATION-CLASS (D45 / notice 47b). It merges only when Alex says so, and no
merge-on-silence default exists. The release that runs it also starts the code
that writes it, both consumers on worker-ws, and that code needs the table.

ROLLBACK. Rows drain only while this code runs, so read the count BEFORE
reverting the code: ``SELECT count(*) FROM owed_chart_points``. If it is not 0,
wait while the new code pays them. Then roll the code back, and only then

    alembic downgrade kalshi_archive_store_683

Rows committed after that read and before the revert stay in the table
unpaid. The old code never reads them, and the downgrade drops them, which
loses those points. Downgrading while the new code runs would fail every due
stamp. Leaving the table in place after a code revert is harmless.

Revision ID: owed_chart_points_11181
Revises: kalshi_archive_store_683
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "owed_chart_points_11181"
down_revision = "kalshi_archive_store_683"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owed_chart_points",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("reading", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_owed_chart_points_source_id", "owed_chart_points", ["source", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_owed_chart_points_source_id", table_name="owed_chart_points")
    op.drop_table("owed_chart_points")
