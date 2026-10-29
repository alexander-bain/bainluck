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
keeps the batch safe either way. Neither index is in the GIN flush task's
lists, so no flush holds their lock.

HOW THE TABLE LOCK IS TAKEN (v5958). The first release of this revision lost
the lock on all six of env.py's attempts (12 s each, 2026-10-29 21:42:05Z to
21:43:35Z), and every price write that arrived meanwhile queued behind the
waiting request. `events` is never free of long readers: ten production
snapshots between 21:58Z and 22:06Z found a transaction holding `events` aged
12 s or more in seven, and 2 s or more in eight of nine; one minute-cadence
task alone (`transition_event_statuses`, 6-124 s a run) held it through
attempts 2 and 3. A wait of any useful length therefore queues writers, and a
blind short wait mostly fails. So the request is made only at a quiet moment:

* nothing to do (both indexes already `fastupdate=off`, or absent) takes no
  lock at all, which is also how an attended apply ahead of the release
  turns the release into a plain version stamp;
* otherwise the catalogue is polled every :data:`GATE_POLL_S` until no session
  holding a lock on `events` or one of its indexes has a transaction older
  than :data:`GATE_HOLDER_AGE_S`, and only then is the lock requested, under a
  :data:`LOCK_TRY_TIMEOUT_MS` `lock_timeout`, in a savepoint so a refusal
  leaves the batch clean;
* at most :data:`MAX_LOCK_TRIES` requests within :data:`GATE_BUDGET_S`, then
  :class:`EventsLockNotTaken`, which is not a lock timeout, so env.py's retry
  does not multiply the budget and the release fails cleanly at the head check.

Worst cost: one writer stall of at most 1.5 s per request, at most 8 requests
(12 s summed, never consecutive: each follows a fresh quiet gate), inside a
batch that ends by 60 s plus 8 x 1.5 s = 72 s, under
`migration_lock_budget.RELEASE_PHASE_BUDGET_S` (120 s).

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

import logging
import time

from alembic import op
from sqlalchemy import text

from app.utils.repair_lock_budget import is_lock_timeout

logger = logging.getLogger("alembic.runtime.migration")

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

#: See HOW THE TABLE LOCK IS TAKEN in the module docstring.
GATE_POLL_S = 0.25
GATE_HOLDER_AGE_S = 1.0
GATE_BUDGET_S = 60.0
LOCK_TRY_TIMEOUT_MS = 1500
MAX_LOCK_TRIES = 8

#: How many of :data:`INDEXES` exist with `fastupdate=off`, and how many exist.
#: A catalogue read: it takes no lock on `events`.
STATE_SQL = (
    "SELECT count(*) FILTER (WHERE 'fastupdate=off' = ANY(coalesce(c.reloptions, '{}'))),"
    " count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid"
    " WHERE i.indrelid = 'events'::regclass AND c.relname = ANY(:names)"
)

#: Sessions holding a granted lock on `events` or one of its indexes whose
#: transaction is older than the gate. `clock_timestamp()`, not `now()`: this
#: transaction's own start would freeze the comparison.
GATE_SQL = (
    "SELECT count(DISTINCT a.pid) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid"
    " WHERE l.locktype = 'relation' AND l.granted AND a.pid <> pg_backend_pid()"
    " AND (l.relation = 'events'::regclass OR l.relation IN"
    " (SELECT indexrelid FROM pg_index WHERE indrelid = 'events'::regclass))"
    " AND a.xact_start < clock_timestamp() - make_interval(secs => :age)"
)


class EventsLockNotTaken(RuntimeError):
    """No quiet moment on `events` within the budget. Not a lock timeout, by design."""


def _state(bind) -> tuple[int, int]:
    off, present = bind.execute(text(STATE_SQL), {"names": list(INDEXES)}).one()
    return int(off), int(present)


def take_events_lock(bind, sleep=time.sleep, clock=time.monotonic) -> int:
    """Take statement 0 at a quiet moment; return the number of requests made.

    Alembic runs the batch in one transaction, and `pg_stat_activity` keeps the
    copy taken at its first read in a transaction, while `pg_locks` is live; so
    every poll first discards that copy, as its own statement (#11757 review).
    """
    bind.execute(text(f"SET LOCAL lock_timeout = '{int(LOCK_TRY_TIMEOUT_MS)}ms'"))
    deadline = clock() + GATE_BUDGET_S
    tries = 0
    while True:
        bind.execute(text("SELECT pg_stat_clear_snapshot()"))
        busy = bind.execute(text(GATE_SQL), {"age": GATE_HOLDER_AGE_S}).scalar_one()
        if not busy:
            tries += 1
            bind.execute(text("SAVEPOINT events_lock"))
            try:
                bind.execute(text(LOCK_EVENTS))
            except Exception as exc:  # noqa: BLE001 - only a lock timeout is retried
                if not is_lock_timeout(exc):
                    raise
                bind.execute(text("ROLLBACK TO SAVEPOINT events_lock"))
                if tries >= MAX_LOCK_TRIES:
                    raise EventsLockNotTaken(
                        f"events lock refused on all {tries} quiet-moment requests"
                    ) from None
            else:
                bind.execute(text("RELEASE SAVEPOINT events_lock"))
                return tries
        if clock() >= deadline:
            raise EventsLockNotTaken(
                f"no quiet moment on events within {GATE_BUDGET_S:.0f} s ({tries} requests)"
            )
        sleep(GATE_POLL_S)


def _run(batch: tuple[str, ...], done) -> None:
    bind = op.get_bind()
    off, present = _state(bind)
    if done(off, present):
        logger.info(
            "#10090 %s: nothing to change (%s of %s present indexes fastupdate=off); "
            "no lock taken",
            revision, off, present,
        )
        return
    tries = take_events_lock(bind)
    logger.info("#10090 %s: events lock taken on request %s", revision, tries)
    try:
        for statement in batch[1:]:
            op.execute(statement)
    except Exception as exc:  # noqa: BLE001 - see EventsLockNotTaken
        # Holding the table, an ALTER can wait only on a direct index locker.
        # Re-raised as a lock timeout, env.py would rerun the whole gate.
        if not is_lock_timeout(exc):
            raise
        raise EventsLockNotTaken(f"an ALTER waited past the lock_timeout: {exc}") from None


def upgrade() -> None:
    _run(UPGRADE_SQL, lambda off, present: off == present)


def downgrade() -> None:
    _run(DOWNGRADE_SQL, lambda off, present: off == 0)
