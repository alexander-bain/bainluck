"""#10090: the two `events` full-text GIN indexes take their entries directly too.

THE SHIP. A live score or price write on `events` never stops for seconds to
merge a search index's backlog inside its own statement.

THE GAP. `events_gin_fastupdate_off` set `fastupdate = off` on the GIN indexes
any migration creates on `events`. Production carries two more that no
migration creates, so neither that migration's list nor its census saw them.
The integrator's G2 readback (v5955, 2026-10-29 19:04Z) found them with no
reloptions. Production read 2026-10-29 19:45Z (db-query, receipt
artifacts/latency-10090-fts-gin-20261029T1945Z/idxdef.json):

    ix_events_fts_home  oid 1027976  gin (to_tsvector('english',
                        COALESCE(home_team_name, '')::text))   4.9 MB
    ix_events_fts_away  oid 1028003  the same on away_team_name  5.0 MB

Both are used (idx_scan 2,070,976 each, the full-text arm of
`/api/events/search`), so they are kept. Both still have GIN's default
`fastupdate = on` and the default 4 MB `gin_pending_list_limit`. An expression
index joins every non-HOT update of its table, whatever columns changed, and
46% of `events` updates are non-HOT (n_tup_upd 62,237,652, n_tup_hot_upd
33,538,429, same read). So a price write still appends to both lists, and the
writer whose append crosses 4 MB merges the whole list inside its own
statement, with its row locked. That is the stall the parent revision closed
for the other three.

WHAT THIS DOES, EXHAUSTIVELY: one storage parameter on each of two indexes,
under one table lock held for the batch. No column, no data, no scan, no index
build (gotcha #31 does not apply). Both ALTERs use `IF EXISTS`, because no
migration creates these indexes: a database built from migrations alone
does not have them, and there the upgrade is a no-op. The entries already
pending stay readable and are emptied by the next autovacuum of `events`. With
the option off, no writer adds to either list again.

LOCKS. As in the parent: `LOCK TABLE events IN ACCESS EXCLUSIVE MODE` first, so
a query arriving mid-batch waits at the table holding no index lock.
Production's OIDs ascend in this batch's order today, so the two ALTERs alone
would not deadlock a query that locks indexes in OID order. A REINDEX
CONCURRENTLY of the home index would reverse that order, and the table lock
keeps the batch safe either way. `alembic/env.py` arms the 5 s `lock_timeout`
and `run_with_lock_retry` (4 attempts). The realistic wait is one per attempt,
4 x 5 s + 3 x 2 s = 26 s, and the ceiling is 3 locks x 5 s x 4 + 6 s = 66 s,
under `migration_lock_budget.RELEASE_PHASE_BUDGET_S`. Neither index is in the
GIN flush task's lists, so no flush holds their lock.

COST. Each non-HOT `events` write pays two small direct GIN inserts instead of
an occasional 4 MB merge. Each tsvector here is a team name, a few lexemes.

MIGRATION-CLASS (D45 / notice 47b). It lands only on Alex's word, through the
Integrator, with its exact gates and a production readback. No default fires
on silence.

Reversible. The D51 undo line restores the GIN default on these two and leaves
the parent's three as they are:

    alembic downgrade events_gin_fastupdate_off

Revision ID: events_fts_gin_fastupdate_off
Revises: events_gin_fastupdate_off
Create Date: 2026-10-29
"""

from alembic import op

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "events_fts_gin_fastupdate_off"
down_revision = "events_gin_fastupdate_off"
branch_labels = None
depends_on = None

#: Production's two out-of-band full-text GIN indexes, in production OID order.
INDEXES: tuple[str, ...] = (
    "ix_events_fts_home",
    "ix_events_fts_away",
)

#: Statement 0 of both batches. See LOCKS in the module docstring.
LOCK_EVENTS = "LOCK TABLE events IN ACCESS EXCLUSIVE MODE"
UPGRADE_SQL: tuple[str, ...] = (LOCK_EVENTS,) + tuple(
    f"ALTER INDEX IF EXISTS {name} SET (fastupdate = off)" for name in INDEXES
)
DOWNGRADE_SQL: tuple[str, ...] = (LOCK_EVENTS,) + tuple(
    f"ALTER INDEX IF EXISTS {name} RESET (fastupdate)" for name in INDEXES
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
