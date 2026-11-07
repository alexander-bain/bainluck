"""#12095 Decide 37-B: a store for ranking slates, and two event columns.

THE SHIP. Every ranking change is scored against Alex's grades before it
ships, and real readers' swipes slot in on day one with no rework. This
revision only creates the places the harness writes; no reader-facing request
reads them and nothing a reader sees changes.

WHAT THIS DOES, EXHAUSTIVELY.

* Creates a new, empty table ``ranking_slate_snapshots`` (one row per
  captured slate: served order + candidates as JSONB) and its two b-tree
  indexes. Built on an empty table, so gotcha #31 has nothing to apply to.
* Creates one new, empty table ``ranking_grades`` (one row per grader per card
  of a slate, written by the Phase 2 admin grading page) and its two indexes.
* Adds two NULLABLE columns with NO default to ``discover_interactions``:
  ``slate_id`` and ``ranker_version`` (VARCHAR 64). On PostgreSQL that is a
  catalog-only change — no table rewrite, no backfill, existing rows read NULL
  ("not recorded").

LOCKS. ``ADD COLUMN`` takes a brief ACCESS EXCLUSIVE lock on
``discover_interactions``; its only writer is ``POST /api/feed/interactions``
(a few hundred rows a week) and nothing reads it on a request path. The
bounded ``lock_timeout`` that ``alembic/env.py`` arms for every migration caps
the wait, so the release fails cleanly instead of queueing writers behind it.
No foreign key anywhere.

ENABLING NOTHING. The only writers stay inert unless ``RANKING_SNAPSHOTS`` is on.

MIGRATION-CLASS (D45 / notice 47b). It lands only on Alex's word. No default
fires on silence.

Reversible. The undo line is

    alembic downgrade stream_observed_spans_11929

which drops both tables (and their slates and grades) and the two columns
(and what they hold).

Revision ID: ranking_slates_12095
Revises: stream_observed_spans_11929
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "ranking_slates_12095"
down_revision = "stream_observed_spans_11929"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ranking_slate_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("surface", sa.String(32), nullable=False),
        sa.Column("slate_id", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ranker_version", sa.String(64), nullable=False),
        sa.Column("served_order", postgresql.JSONB(), nullable=False),
        sa.Column("candidates", postgresql.JSONB(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_ranking_slates_surface_captured",
        "ranking_slate_snapshots",
        ["surface", "captured_at"],
    )
    op.create_index("ix_ranking_slates_slate_id", "ranking_slate_snapshots", ["slate_id"])

    op.create_table(
        "ranking_grades",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("slate_id", sa.String(64), nullable=False),
        sa.Column("surface", sa.String(32), nullable=False),
        sa.Column("grader", sa.String(40), nullable=False),
        sa.Column("expert", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column(
            "graded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "grade IN ('shareable', 'interesting', 'neither')", name="ck_ranking_grades_grade"
        ),
    )
    op.create_index("ix_ranking_grades_slate", "ranking_grades", ["slate_id", "grader"])
    op.create_index("ix_ranking_grades_graded_at", "ranking_grades", ["graded_at"])

    op.add_column("discover_interactions", sa.Column("slate_id", sa.String(64), nullable=True))
    op.add_column(
        "discover_interactions", sa.Column("ranker_version", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("discover_interactions", "ranker_version")
    op.drop_column("discover_interactions", "slate_id")
    op.drop_index("ix_ranking_grades_graded_at", table_name="ranking_grades")
    op.drop_index("ix_ranking_grades_slate", table_name="ranking_grades")
    op.drop_table("ranking_grades")
    op.drop_index("ix_ranking_slates_slate_id", table_name="ranking_slate_snapshots")
    op.drop_index("ix_ranking_slates_surface_captured", table_name="ranking_slate_snapshots")
    op.drop_table("ranking_slate_snapshots")
