"""#10090: `ix_futures_outcomes_name_trgm` takes its entries directly. No pending list.

THE SHIP. A changed live probability is not held behind a futures write that
stops for one to two seconds to empty a search index's backlog.

THE DEFECT. The trigram index on `futures_outcomes.name` was created with
PostgreSQL's GIN default, `fastupdate = on`. Each new row version is appended
to a pending list, and the list is merged into the index once it passes
`gin_pending_list_limit` (4 MB on production). That merge runs inside whichever
statement crosses the limit. Almost no `futures_outcomes` update is HOT (1.5%
on 2026-10-12): `last_updated` and `rank` are both indexed. So every price
write and every field rerank adds to the list, and the socket's own price phases
regularly pay the merge. The worker-ws minute line at 16:01:53Z on release 5671
recorded a nonlive phase with `db.rerank=2.02s` while its price saves took
0.02s.

MEASURED (local PG14, a SYNTHETIC 1.98M-row table, not a production copy,
carrying the nine production index definitions;
artifacts/live-iteration-goal-20261011/rerank-10090/). 60,000 single-row price
writes: max 1,556 ms with fastupdate on, 38 ms with it off; median 0.37 ms to
0.47 ms. The shipped Kalshi flush on that table, with a live leg changing every
500 ms while 79 non-live markets were written every 250 ms, rerank plan held
constant: in two parent runs the merge stalled single statements for up to
2.7 s and the live price waited up to 2.67 s; in two candidate runs no price or
nested-loop rerank statement exceeded 0.4 s and the live price waited at most
0.90 s. The median phase rose from about 12 ms to 45 ms. That is the price of
the merge being paid evenly instead of all at once.

WHAT THIS DOES, EXHAUSTIVELY: one storage parameter on one index. No column,
no data, no scan, no index build (gotcha #31 does not apply). The entries already
pending stay readable and are merged by the next autovacuum of
`futures_outcomes`. With the option off, no writer adds to that list again.

LOCKS. `ALTER INDEX ... SET (fastupdate)` takes ACCESS EXCLUSIVE on the index,
so it waits behind any open `futures_outcomes` writer and blocks new ones
while it waits. `alembic/env.py` sets the connection's `lock_timeout` and wraps
the batch in `run_with_lock_retry`, so a long poller transaction makes this
retry instead of queueing the socket behind it. Once granted, it is a catalog
write.

MIGRATION-CLASS (D45 / notice 47b): merged only on Alex's word, and no default
fires on silence.

Reversible. The D51 undo line restores the GIN default:

    alembic downgrade activitykit_observation

Revision ID: fo_trgm_fastupdate_off
Revises: activitykit_observation
Create Date: 2026-10-12
"""

from alembic import op

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "fo_trgm_fastupdate_off"
down_revision = "activitykit_observation"
branch_labels = None
depends_on = None

INDEX = "ix_futures_outcomes_name_trgm"

UPGRADE_SQL = f"ALTER INDEX IF EXISTS {INDEX} SET (fastupdate = off)"
DOWNGRADE_SQL = f"ALTER INDEX IF EXISTS {INDEX} RESET (fastupdate)"


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
