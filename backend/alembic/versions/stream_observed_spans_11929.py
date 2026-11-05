"""#11929 Decide 27-B: a store for observed spans — a span, not a row.

THE SHIP. A market we were reading the whole time never shows a hole. The
per-row keep-alive writes a chart point per live leg every 15 minutes (about
3.3M rows a day, holding only about 32 minutes on Kalshi on Nov 4). A span
records the same observation once per stretch; ``/history`` draws it flat at
serve time (a later PR). This revision only creates the place spans are kept.

WHAT THIS DOES, EXHAUSTIVELY. It creates two new, empty tables, their
constraints, and three b-tree indexes (two named, plus the primary keys). It
writes no data, alters no existing table and adds no column. The indexes are
built on empty tables, so gotcha #31 (no ``CREATE INDEX CONCURRENTLY`` in a
migration) has nothing to apply to.

* ``stream_observed_spans``: one row per stretch a socket consumer saw one leg
  live. ``ended_at`` NULL while open. ``ix_sos_outcome_started`` serves the
  per-leg chart read; the partial ``ix_sos_open_by_venue`` serves the
  run-start recovery of spans a dead run left open.
* ``stream_span_heartbeats``: per venue, the last committed tick, which bounds
  every open span for a reader.

LOCKS. None on any existing table: there is deliberately no foreign key to
``futures_outcomes`` (#12020's foreign key took SHARE ROW EXCLUSIVE there and
eight live Kalshi flushes hit their lock timeout during that second).

ENABLING NOTHING. Executing this turns nothing on. The only writer,
``app/utils/stream_observed_spans.py``, does nothing unless
``STREAM_OBSERVED_SPANS`` names a venue whose ``STREAM_HISTORY_POINTS`` is on.

MIGRATION-CLASS (D45 / notice 47b). It lands only on Alex's word, through the
Integrator. No default fires on silence.

Reversible. The undo line is

    alembic downgrade venue_history_points_11929

which drops both tables and whatever they hold.

Revision ID: stream_observed_spans_11929
Revises: venue_history_points_11929
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "stream_observed_spans_11929"
down_revision = "venue_history_points_11929"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stream_observed_spans",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name="ck_sos_order"
        ),
        sa.CheckConstraint("venue IN ('kalshi', 'polymarket')", name="ck_sos_venue"),
    )
    op.create_index(
        "ix_sos_outcome_started",
        "stream_observed_spans",
        ["outcome_id", "started_at"],
    )
    op.create_index(
        "ix_sos_open_by_venue",
        "stream_observed_spans",
        ["venue"],
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "stream_span_heartbeats",
        sa.Column("venue", sa.Text(), primary_key=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stream_span_heartbeats")
    op.drop_index("ix_sos_open_by_venue", table_name="stream_observed_spans")
    op.drop_index("ix_sos_outcome_started", table_name="stream_observed_spans")
    op.drop_table("stream_observed_spans")
