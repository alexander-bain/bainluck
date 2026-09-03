"""One game, one authority id: UNIQUE on events.espn_id.

#2693 step 2, lane1/058. ``events.espn_id`` is the column ``espn_sync`` steers
every status, ``commence_time``, ``completed_at`` and win-probability
correction through. Measured on production 2026-09-02, **196 ESPN event ids
were worn by 430 rows across 13 sports** — so the authority was writing one
game's truth onto two fixtures, which is how a US Open card printed "Final"
over a match in its fourth set (lane1/057).

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

═══ PARTIAL, BECAUSE NULL IS THE ORDINARY STATE ═══

``WHERE espn_id IS NOT NULL``. Most events never carry one — 30,199 tennis rows
carried none at all until lane1/057 — and Postgres would allow the NULLs
regardless, but the partial form keeps the index the size of the population
that actually has the property and states the invariant honestly: *a row need
not have an authority id; a row may not share one*.

═══ DEPLOY SAFETY, AND WHY THERE IS NO CONCURRENTLY ═══

Gotcha #31 says never ``CREATE INDEX CONCURRENTLY`` in Alembic: the Heroku
release phase times out around five minutes and a half-built index is worse
than none. This index is small — measured 2026-09-02, ~208,000 events carry a
non-null ``espn_id``, and a unique btree over that builds in a few seconds, well
inside the window. It is stated here so the next person does not have to
re-measure to know why the rule was not invoked.

``ix_events_espn_id`` (the existing NON-unique index) is dropped in the same
step. Two btrees over one column is one write amplification too many, and
leaving the loose one behind would let a future reader conclude the column is
not constrained.

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
