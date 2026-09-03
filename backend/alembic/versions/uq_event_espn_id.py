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

**Step 2 — the one command, and only once step 1 prints ``0``.** Attended, on a
merged branch, because on Heroku it is the release phase that applies it::

    git -c push.default=simple push origin master

That is the whole of it: there is **no manual DDL to run**. The release phase's
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
Revises: match_receipts
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "uq_event_espn_id"
down_revision = "match_receipts"
branch_labels = None
depends_on = None

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


def upgrade() -> None:
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
        "events",
        ["espn_id"],
        unique=True,
        postgresql_where=sa.text("espn_id IS NOT NULL"),
    )
    # Redundant now: a unique btree on the same column serves every lookup the
    # old one did.
    op.drop_index(OLD_INDEX_NAME, table_name="events")


def downgrade() -> None:
    # Restore the loose index FIRST, so there is never a window in which the
    # column has no index at all — `espn_sync` looks up through it on every
    # correction.
    op.create_index(OLD_INDEX_NAME, "events", ["espn_id"])
    op.drop_index(INDEX_NAME, table_name="events")
