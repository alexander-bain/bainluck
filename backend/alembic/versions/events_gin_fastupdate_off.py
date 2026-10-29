"""#10090: the `events` GIN indexes take their entries directly. No pending lists.

THE SHIP. A live score or price write on `events` never stops for seconds to
merge a search index's backlog inside its own statement.

THE DEFECT. All five GIN indexes on `events` were created with PostgreSQL's
GIN default, `fastupdate = on`. Each new row version is appended to a pending
list, and the writer whose append crosses `gin_pending_list_limit` merges the
whole list inside its own statement, with its row still locked. Mapped on
production 2026-10-29 04:39Z: a single-row `UPDATE events` active >= 9.9 s,
the price stamps for the same row queued behind it on `transactionid`, and
autovacuum's ANALYZE queued behind it on the GIN metapage lock. Which index
that statement merged is not known, so all five are covered.

Production read 2026-10-29 15:47Z (step 0, db-query): every index valid;
`ix_events_home_team_name_trgm` and `ix_events_event_tags` carry no reloptions
(the 4 MB default list); the other three carry `gin_pending_list_limit=256`.
None carried `fastupdate`. Receipt:
artifacts/10090-closure-board-20261028/gin-ddl/step0-precheck-20261029T1547Z.json

WHAT THIS DOES, EXHAUSTIVELY: one storage parameter on each of five indexes. No
column, no data, no scan, no index build (gotcha #31 does not apply). Existing
reloptions (`gin_pending_list_limit`) are kept. The entries already pending
stay readable and are emptied by the GIN flush task or the next autovacuum of
`events`; with the option off, no writer adds to a list again.

`ix_events_{home,away}_team_name_trgm` duplicate `ix_events_{home,away}_trgm`
and are being dropped in attended psql (Alex, 2026-10-29). They are listed here
with `IF EXISTS`, so the order of the drop and this release does not matter:
before the drop they stop merging too, after it they are skipped.

LOCKS. `ALTER INDEX ... SET (fastupdate)` takes ACCESS EXCLUSIVE on the index.
Planning any query on `events` opens all of its indexes, so while the ALTER
waits, every new `events` reader and writer queues behind it. `alembic/env.py`
sets the connection's `lock_timeout` (5 s) and wraps the batch in
`run_with_lock_retry` (4 attempts), so a straggler makes this retry instead of
queueing the site behind it. Once the first ALTER is granted, any transaction
that planned an `events` query has finished, so the rest wait only on a direct
`gin_clean_pending_list` of a later index (the flush task, up to its 15 s
per-index timeout); the same lock timeout bounds that wait. Once granted, it is
a catalog write.

COST. Each non-HOT `events` write pays its GIN inserts directly instead of
batching them. The `fo_trgm_fastupdate_off` precedent measured single-row
writes at a median of 0.37 -> 0.47 ms and a max of 1,556 -> 38 ms (synthetic).

MIGRATION-CLASS (D45 / notice 47b). Alex approved this change on 2026-10-29
("Approve both", ALEX-DECISIONS item 26). It still lands only through the
Integrator, its exact gates and a production readback. No default fires on
silence.

Reversible. The D51 undo line restores the GIN default (and keeps the
`gin_pending_list_limit` values):

    alembic downgrade dnpl_retirement_10090

Revision ID: events_gin_fastupdate_off
Revises: dnpl_retirement_10090
Create Date: 2026-10-29
"""

from alembic import op

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "events_gin_fastupdate_off"
down_revision = "dnpl_retirement_10090"
branch_labels = None
depends_on = None

#: The write-path index first, then the kept trigram pair, then the duplicates.
INDEXES: tuple[str, ...] = (
    "ix_events_event_tags",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_home_team_name_trgm",
    "ix_events_away_team_name_trgm",
)

UPGRADE_SQL: tuple[str, ...] = tuple(
    f"ALTER INDEX IF EXISTS {name} SET (fastupdate = off)" for name in INDEXES
)
DOWNGRADE_SQL: tuple[str, ...] = tuple(
    f"ALTER INDEX IF EXISTS {name} RESET (fastupdate)" for name in INDEXES
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
