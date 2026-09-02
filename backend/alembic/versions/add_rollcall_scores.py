"""Add rollcall_scores — the daily ground-truth roll call scorecard.

One row per (date, league). New empty table: no data movement, no index built
over an existing relation, no CONCURRENTLY (gotcha #31). The unique index is
created on an empty table, so the release phase cost is the CREATE itself.

Revision ID: add_rollcall_scores
Revises: anchors_and_captures
Create Date: 2026-08-28
"""

revision = "add_rollcall_scores"
down_revision = "anchors_and_captures"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        "rollcall_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("league", sa.String(length=40), nullable=False),
        sa.Column("axiom", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("events_external", sa.Integer(), nullable=False, server_default="0"),
        # `graded` is the denominator every other counter is over:
        # events_external minus the fixtures the binder REFUSED to bind
        # (CERT-434). Stored rather than derived so the API and the Redis
        # mirror cannot disagree about what a day's coverage percentage means.
        sa.Column("graded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ambiguous", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_1", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dupes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mis_stamped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clean", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("per_source", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verdict", sa.String(length=24), nullable=False),
        sa.Column("offenders", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("score_date", "league", name="uq_rollcall_date_league"),
    )
    op.create_index(
        "ix_rollcall_scores_score_date", "rollcall_scores", ["score_date"], unique=False
    )


def downgrade():
    op.drop_index("ix_rollcall_scores_score_date", table_name="rollcall_scores")
    op.drop_table("rollcall_scores")
