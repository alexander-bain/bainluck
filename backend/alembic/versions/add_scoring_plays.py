"""Add scoring_plays table for persistent play-by-play history.

Enables correlating specific plays with odds movements for better
line-movement explanations.

Revision ID: add_scoring_plays
Revises: merge_mm_oscars
Create Date: 2026-03-17
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_scoring_plays"
down_revision: Union[str, None] = "merge_mm_oscars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scoring_plays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("period", sa.String(30), nullable=True),
        sa.Column("game_clock", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("play_type", sa.String(50), nullable=True),
        sa.Column("team_name", sa.String(100), nullable=True),
        sa.Column("player_name", sa.String(100), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scoring_plays_event_id", "scoring_plays", ["event_id"])
    op.create_index("ix_scoring_plays_captured_at", "scoring_plays", ["captured_at"])
    # Composite index for dedup checks during live sync
    op.create_index(
        "ix_scoring_plays_dedup",
        "scoring_plays",
        ["event_id", "source", "period", "game_clock"],
    )


def downgrade() -> None:
    op.drop_index("ix_scoring_plays_dedup", table_name="scoring_plays")
    op.drop_index("ix_scoring_plays_captured_at", table_name="scoring_plays")
    op.drop_index("ix_scoring_plays_event_id", table_name="scoring_plays")
    op.drop_table("scoring_plays")
