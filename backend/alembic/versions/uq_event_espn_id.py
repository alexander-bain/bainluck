"""One game, one authority id: UNIQUE on events.espn_id.

#2693 step 2, lane1/058, held open by lane1/065. ``events.espn_id`` is the
column ``espn_sync`` steers every status, ``commence_time``, ``completed_at``
and win-probability correction through. Measured on production 2026-09-02 and
**re-measured 2026-09-03T06:5xZ, unchanged: 196 ESPN event ids worn by 430 rows
across 13 sports** — so the authority was writing one game's truth onto two
fixtures, which is how a US Open card printed "Final" over a match in its
fourth set (lane1/057).

The repair rail ``authority-id-collisions`` hands the id back on every row that
is not the game. This index is what stops the population re-growing: without
it, the same matcher makes the same collision again next week and the repair
becomes a chore instead of a fix.

═══ PRECONDITION — THIS MIGRATION FAILS IF THE REPAIR HAS NOT RUN ═══

``CREATE UNIQUE INDEX`` over a colliding column raises, and on Heroku a raising
release phase means **the site does not deploy at all**. So this is not a
migration to run hopefully. Before deploying it, this must return zero rows::

    SELECT espn_id, count(*) FROM events
    WHERE espn_id IS NOT NULL
    GROUP BY espn_id HAVING count(*) > 1;

``upgrade()`` asks that question itself and raises with the count and the first
few offenders rather than letting Postgres raise a `duplicate key` the operator
then has to go and diagnose. A precondition worth having is worth stating in
the error.

**The precondition is not met today, and the reason is named.** The repair
resolves 188 of the 196; the other 8 groups (17 rows) it deliberately refuses,
because ESPN cannot settle which of our rows is really that game — 2 where the
authority itself gave no answer (one 502, one 404), 6 where ESPN answered and
recognised neither row. They are filed as **#2769** under D42 = A. Four of them
are team-identity variants that #1204 clears as a by-product; two are genuine
mis-anchors. **Merging this file before those 8 clear installs nothing and tells
nobody**, because ``backend/Procfile`` wraps ``alembic upgrade heads`` in
``|| echo`` and swallows the raise (#2741). Order: repair drains 188 → the 8
clear → this ships into a tree where it can succeed.

═══ PARTIAL, BECAUSE NULL IS THE ORDINARY STATE ═══

``WHERE espn_id IS NOT NULL``. Most events never carry one — 30,199 tennis rows
carried none at all until lane1/057 — and Postgres would allow the NULLs
regardless, but the partial form keeps the index the size of the population
that actually has the property and states the invariant honestly: *a row need
not have an authority id; a row may not share one*.

═══ DEPLOY SAFETY, AND WHY THERE IS NO CONCURRENTLY ═══

Gotcha #31 says never ``CREATE INDEX CONCURRENTLY`` in Alembic: the Heroku
release phase times out around five minutes and a half-built index is worse
than none. Two facts make the rule unnecessary here rather than merely
survivable, both measured on production 2026-09-03T06:5xZ:

* **The population is small.** ``count(espn_id)`` is **8,335** of 236,786 rows —
  8,101 of them distinct — and the existing ``ix_events_espn_id`` over the same
  column is 9,240 kB. A unique btree over 8,335 entries builds in well under a
  second; the cost is the one heap pass over the 542 MB table to find them.
  *(An earlier draft of this file said "~208,000 events carry a non-null
  espn_id". That was wrong by 25× — it was the row count, not the column's
  non-null count. The conclusion it supported is unchanged and in fact stronger,
  but the number is corrected rather than left standing.)*
* **Non-concurrent is atomic.** A plain ``CREATE UNIQUE INDEX`` runs inside the
  migration's transaction, so a failed attempt leaves nothing behind and the
  revision is not stamped — the next deploy simply retries. ``CONCURRENTLY``
  cannot run in a transaction and leaves an ``INVALID`` index when it fails,
  which is precisely the half-built state gotcha #31 is about.

``ix_events_espn_id`` (the existing NON-unique index) is dropped in the same
step. Two btrees over one column is one write amplification too many, and
leaving the loose one behind would let a future reader conclude the column is
not constrained. The partial unique index serves every lookup the old one did:
Postgres can prove ``espn_id = $1`` implies ``espn_id IS NOT NULL``, which is
the only shape ``espn_sync`` uses. A scan for ``espn_id IS NULL`` loses the
index and is a sequential scan either way — 228,451 of the 236,786 rows.

═══ LOCK DISCIPLINE — ONE TABLE, ONE ACQUISITION, STRONGEST MODE, FIRST ═══

#2782 cost four failed releases and ~50 minutes of stale production on the night
of 2026-09-02: ``link_loss_receipts`` took ``market_match_receipts`` and then
``futures_markets``, the application takes them the other way round, and the two
formed a cycle. ``should_retry`` in ``app/utils/migration_lock_budget`` refuses
anything that is not a lock timeout — correctly — so a ``DeadlockDetected`` was
fatal on every attempt.

**This migration is not in that cross-table class**, and saying otherwise would
be inheriting someone else's diagnosis. It touches exactly one table, ``events``
(``test_it_touches_exactly_one_table`` holds that), so there is no pair to
invert. What it *did* have was the same underlying mistake in a single-table
form: it took **three progressively stronger locks** on ``events`` — ``ACCESS
SHARE`` for the pre-check, ``SHARE`` for the index build, ``ACCESS EXCLUSIVE``
for the drop — reaching its peak mode last, after all the expensive work. Three
consequences, all removed by taking the strongest lock first:

* **The pre-check was not atomic with the build.** Between the ``SELECT`` that
  counts contested ids and the ``CREATE UNIQUE INDEX``, nothing stopped a writer
  inserting a row that collides. Postgres would then raise ``duplicate key`` —
  precisely the unhelpful error the pre-check exists to replace — and the
  Procfile's ``|| echo`` (#2741) would swallow it. Holding ``ACCESS EXCLUSIVE``
  from the first statement makes the count an answer about the table the index
  is built over, not about the table as it was a second and a half ago.
* **A failed attempt threw away the build.** The ``ACCESS EXCLUSIVE`` request
  came *after* the heap pass, so contention was discovered at the most expensive
  possible moment and the retry repeated the work. Now an attempt that cannot
  have the table costs one lock wait and no work.
* **A lock upgrade is a deadlock shape.** Postgres has a queue-jump heuristic
  that usually saves a self-upgrade, but "usually" is not a property to build an
  invariant on, and a deadlock here is the one error the retry budget will not
  retry. One acquisition cannot be upgraded.

``lock_timeout`` is set explicitly by this file rather than inherited silently
from ``alembic/env.py``'s connect-time option, and it is read from
:func:`app.utils.migration_lock_budget.resolve_settings` so the two cannot
diverge and ``ALEMBIC_LOCK_TIMEOUT_MS`` still overrides both.

**There is deliberately no retry inside this file.** ``env.py`` already wraps the
whole batch in ``run_with_lock_retry`` (4 attempts, 5s timeout, 2s backoff). A
second loop nested inside it would multiply, not add: 4 x 4 attempts x 5s is 80s
of lock waiting plus backoff, against a ``RELEASE_PHASE_BUDGET_S`` of 120s that
also has to import the app and stamp a version. The outer budget is the budget.

**Measured, so the window is a number and not an adjective.** A full heap pass
over ``events`` is **1.24s** on production (2026-09-03, ``EXPLAIN ANALYZE`` of a
forced sequential scan: 29,422 blocks, 1,044ms of it I/O). The index build is
that scan plus a sort of 8,335 keys, so ``ACCESS EXCLUSIVE`` is held for roughly
a second and a half — readers of ``events`` wait that long, against the 20s at
which the frontend's API client aborts. The previous shape blocked readers too,
in up to four separate five-second queue windows, and had the build to show for
none of them.

═══ HOW TO LAND IT — THE PRE-CHECK, THEN THE ONE COMMAND ═══

**Step 1 — the pre-check. It must print ``0``.** Read-only; run it from anywhere
with ``source ~/.claude/.env``::

    curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"sql":"SELECT count(*) AS contested_ids FROM (SELECT espn_id FROM events WHERE espn_id IS NOT NULL GROUP BY espn_id HAVING count(*) > 1) t","limit":5}' \
      "$BAINLUCK_API/api/admin/db-query"

Measured 2026-09-03T06:5xZ it prints **196**, so the index cannot land today.
The 188 that the repair resolves come out via the repair rail; the remaining 8
are #2769. The richer form of the same question — which groups, and why each is
refused — is ``backend/scripts/audit_authority_id_collisions.py``, which reaches
its verdicts through the same ``app.utils.authority_id_collisions`` module the
repair job runs, so a dry run and the job cannot drift.

**Step 2 — quiet the writers, release, put them back.** Attended, on a merged
branch, because on Heroku it is the release phase that applies it. #2782 proved
this sequence on the night of 2026-09-02 (it is what finally landed v4020 after
four failures), and it is four lines::

    heroku ps:scale scheduler=0 worker-heavy=0 -a bainluck   # 1. stop the writers
    # 2. wait ~60s for in-flight tasks to commit, then confirm the table is idle:
    #    POST /api/admin/db-query with
    #    SELECT count(*) FROM pg_locks l JOIN pg_class c ON c.oid = l.relation
    #    WHERE c.relname = 'events' AND l.mode <> 'AccessShareLock'  -- expect 0
    git -c push.default=simple push origin master             # 3. release
    heroku ps:scale scheduler=1 worker-heavy=1 -a bainluck    # 4. put them back

**Why those two dynos and not others.** ``scheduler`` is Celery beat: at zero,
no periodic task is dispatched to *any* queue, which is what actually stops new
writers to ``events`` — the heaviest of them, ``sync_espn_live_events`` and
``transition_event_statuses``, are on the **realtime** queue, not ``heavy``, so
scaling ``worker-realtime`` down is neither necessary (beat is already off) nor
sufficient on its own. ``worker-heavy`` goes to zero as well because
``match_prediction_markets`` runs 337s p50 / 699s p95 and a pass already in
flight when beat stops would otherwise keep holding the table for minutes.
``web`` stays up throughout: the site keeps serving, and readers pay the ~1.5s
measured above.

If step 2's count will not go to zero, do **not** raise the lock timeout — that
is what turned #2782's clean ``LockNotAvailable`` into a fatal
``DeadlockDetected``. Find the holder (add ``l.pid, c.relname`` to that query)
and let it finish.

There is **no manual DDL to run**. The release phase's
``alembic upgrade heads`` applies this revision. Do not run ``CREATE UNIQUE
INDEX`` by hand — psql on 5432 is not reachable from the agent sandbox, and a
hand-built index leaves Alembic unstamped so the next deploy tries again and
raises on the index it cannot see it already made.

**Why the pre-check is not optional even though ``upgrade()`` repeats it.**
``backend/Procfile`` wraps the release-phase call in ``|| echo`` (#2741), so a
raise here is swallowed and the deploy proceeds while the invariant silently
does not exist. The pre-check is what makes the failure visible BEFORE it is
swallowed. Until #2741 is ruled on, running this migration hopefully is
indistinguishable from running it successfully.

Revision ID: uq_event_espn_id
Revises: link_change_history
Create Date: 2026-09-02

Re-pointed 2026-09-03 (lane1/065). It originally revised ``match_receipts``, which
has since become a BRANCHPOINT — lane1b's ``link_loss_receipts`` →
``link_change_history`` (#2758) landed off it while this file was out of tree. CI
runs the MERGE ref, so the second head showed up there and not in a local
``alembic heads`` on an un-rebased branch. If this file sits out of tree again,
re-point it at whatever the single head is before restaging.
"""

import os

from alembic import op
import sqlalchemy as sa

from app.utils.migration_lock_budget import resolve_settings

# revision identifiers, used by Alembic.
revision = "uq_event_espn_id"
down_revision = "link_change_history"
branch_labels = None
depends_on = None

TABLE_NAME = "events"
INDEX_NAME = "uq_events_espn_id"
OLD_INDEX_NAME = "ix_events_espn_id"

COLLISION_SQL = sa.text(
    """
    SELECT espn_id, count(*) AS n
    FROM events
    WHERE espn_id IS NOT NULL
    GROUP BY espn_id
    HAVING count(*) > 1
    ORDER BY n DESC, espn_id
    LIMIT 10
    """
)

COLLISION_COUNT_SQL = sa.text(
    """
    SELECT count(*) FROM (
        SELECT espn_id FROM events
        WHERE espn_id IS NOT NULL
        GROUP BY espn_id HAVING count(*) > 1
    ) t
    """
)


def _take_the_table_lock() -> None:
    """The one lock this migration takes: strongest mode, before anything else.

    Every later statement — the pre-check ``SELECT``, the index build, the drop —
    needs a lock on ``events`` that this one already covers, so none of them
    acquires anything and there is no upgrade to deadlock on. It also makes the
    pre-check atomic with the build: no writer can insert a colliding row in
    between. Full argument: the LOCK DISCIPLINE section of the module docstring.

    The timeout comes from the shared budget rather than a literal, so it cannot
    drift from what ``alembic/env.py`` arms at connect time and
    ``ALEMBIC_LOCK_TIMEOUT_MS`` still overrides both. On timeout this raises
    ``LockNotAvailable``, which is the one failure the batch retry in ``env.py``
    is allowed to repeat — cheaply, because no work has been done yet.
    """
    lock_timeout_ms = resolve_settings(os.environ).lock_timeout_ms
    op.execute(f"SET LOCAL lock_timeout = '{int(lock_timeout_ms)}ms'")
    op.execute(f"LOCK TABLE {TABLE_NAME} IN ACCESS EXCLUSIVE MODE")


def upgrade() -> None:
    _take_the_table_lock()
    bind = op.get_bind()

    # THE PRECONDITION, ASKED BEFORE THE DDL. A `duplicate key` from Postgres
    # names one id and no remedy; this names the size of the problem and the
    # rail that fixes it, in the release log the operator is already reading.
    contested = int(bind.execute(COLLISION_COUNT_SQL).scalar() or 0)
    if contested:
        sample = ", ".join(
            f"{row[0]} ({row[1]} rows)" for row in bind.execute(COLLISION_SQL).all()
        )
        raise RuntimeError(
            f"events.espn_id is worn by more than one row for {contested} id(s) — "
            f"the unique index cannot be created. Run the repair first:\n"
            f"  POST /api/admin/repairs/authority-id-collisions?apply=false\n"
            f"  POST /api/admin/repairs/authority-id-collisions?apply=true&plan_hash=<hash>\n"
            f"Worst offenders: {sample}"
        )

    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["espn_id"],
        unique=True,
        postgresql_where=sa.text("espn_id IS NOT NULL"),
    )
    # Redundant now: a unique btree on the same column serves every lookup the
    # old one did.
    op.drop_index(OLD_INDEX_NAME, table_name=TABLE_NAME)


def downgrade() -> None:
    # Same one-acquisition discipline as `upgrade()`: going back also builds an
    # index and drops one, and a downgrade run under contention is a worse place
    # to discover a lock upgrade than a deploy is.
    _take_the_table_lock()
    # Restore the loose index FIRST, so there is never a window in which the
    # column has no index at all — `espn_sync` looks up through it on every
    # correction.
    op.create_index(OLD_INDEX_NAME, TABLE_NAME, ["espn_id"])
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
