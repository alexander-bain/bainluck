"""#1168 — game_moments: THE MOMENTS ENGINE data layer

A key in-game moment = a real-world event (score/home run/goal…) joined to a
win-probability delta, carrying a confidence from the #871 explainability gate.
Rows are precomputed offline (per event) and the history payload surfaces the
confident subset as ``moments:[{ts,label,confidence}]``. MLB first.

Plain index creation (no CREATE INDEX CONCURRENTLY, gotcha #31) — the table
starts empty so index builds are instant.

Revision ID: add_game_moments
Revises: add_search_query_logs
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa

revision = "add_game_moments"
down_revision = "add_search_query_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_moments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moment_type", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("actor_team", sa.String(length=100), nullable=True),
        sa.Column("actor_player", sa.String(length=100), nullable=True),
        sa.Column("period", sa.String(length=30), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("prob_delta", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "event_id", "dedupe_key", name="uq_game_moment_event_key"
        ),
    )
    op.create_index("ix_game_moments_event_id", "game_moments", ["event_id"])
    op.create_index("ix_game_moments_ts", "game_moments", ["ts"])
    op.create_index(
        "ix_game_moments_event_conf", "game_moments", ["event_id", "confidence"]
    )


def downgrade() -> None:
    op.drop_index("ix_game_moments_event_conf", table_name="game_moments")
    op.drop_index("ix_game_moments_ts", table_name="game_moments")
    op.drop_index("ix_game_moments_event_id", table_name="game_moments")
    op.drop_table("game_moments")
