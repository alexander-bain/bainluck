"""Option D (#1866): the narrow typeahead index table.

TABLE ONLY. This migration creates an EMPTY table plus two small btrees and
nothing else. That is condition 1 of the assigned slot
(``.claude/handoff/MIGRATION-SLOT-OPTION-D.md``, assigned by INT-084), and the
other three conditions are honoured as follows — written HERE, in the migration,
because the summary line is what a later window reads and the summary line is
where this gets "helpfully" folded back together:

* **The ~90 MB trigram GIN is NOT in this file** and must never be moved into
  it. It is built out of band with ``CREATE INDEX CONCURRENTLY`` on a one-off
  dyno. **Gotcha #31**: Heroku's release phase has a ~5 min timeout and
  CONCURRENTLY on a large table hangs it — that is the May 22 outage, verbatim.
  The exact DDL ships in the lane's READY file because ``psql``/TCP 5432 egress
  is blocked from an agent session, which makes running it an **ALEX action**.
* **The ~380k-row backfill is a TASK**, not a step in this migration —
  ``app.tasks.typeahead_index.rebuild_typeahead_index``, bounded and resumable.
  Same timeout, same outage class.
* **Revision id is 20 chars** (gotcha #1: <= 32, and Alembic breaks the chain on
  a LATER release, not this one).

THE HEAP-WIDTH ARITHMETIC, because the width IS the mechanism (D3).

The registered sketch assumed ~120 B/row => ~46 MB at ~380k rows. The real
schema is wider and the honest number is bigger. Per row:

    row header + null bitmap                      ~24 B
    id                          BIGINT              8 B
    entity_type                 VARCHAR(24)       ~12 B
    entity_id                   VARCHAR(120)      ~12 B
    display_text                VARCHAR(300)      ~40 B
    search_text                 TEXT              ~50 B
    sport_key                   VARCHAR(60)       ~10 B
    rank_hint                   REAL                4 B
    content_hash                BIGINT              8 B
    is_active                   BOOLEAN             1 B
    refreshed_at                TIMESTAMPTZ         8 B
    ------------------------------------------------------
                                            ~177 B/row

At ~380k rows: **~67 MB heap** (not 46), + PK btree ~10 MB + the unique btree
~20 MB + the out-of-band GIN ~90 MB = **~187 MB total**.

That is **+21 MB against the sketch** and it is stated rather than absorbed.
D3's registered bar (< 200 MB, HALT above 350 MB) still passes — with less
margin than the sketch implied, which is a fact the D3 grading must carry rather
than discover. Two width choices already bought most of it back and are pinned
in the model docstring: ``content_hash`` is a BIGINT and not a 64-char sha256
hex (which alone would have cost 24 MB — more than a third of the heap), and
``rank_hint`` is REAL rather than double.

``FLOAT(24)`` is PostgreSQL's spelling of REAL; it is written that way so the
SQLAlchemy model and the migration agree literally.

Revision ID: add_typeahead_index
Revises: add_device_token_kind
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic. (20 chars — gotcha #1.)
revision = "add_typeahead_index"
down_revision = "add_device_token_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "typeahead_index",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=24), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("display_text", sa.String(length=300), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("sport_key", sa.String(length=60), nullable=True),
        sa.Column(
            "rank_hint",
            sa.Float(precision=24),
            server_default="0",
            nullable=False,
        ),
        sa.Column("content_hash", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_typeahead_index_entity"),
    )
    # Small btree. The reconcile cursor pages on it and the sentinel's staleness
    # scan reads it. Cheap on an EMPTY table, which is why it may ride the
    # release phase while the GIN may not.
    op.create_index(
        "ix_typeahead_index_type_refreshed",
        "typeahead_index",
        ["entity_type", "refreshed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_typeahead_index_type_refreshed", table_name="typeahead_index")
    op.drop_table("typeahead_index")
