"""Add golf_leaderboard_snapshots table for start-of-day deltas.

Revision ID: add_golf_lb_snap
Revises: widen_team_abbrev
Create Date: 2026-04-02
"""

revision = "add_golf_lb_snap"
down_revision = "widen_team_abbrev"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.create_table(
        "golf_leaderboard_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tour", sa.String(20), nullable=False, index=True),
        sa.Column("event_name", sa.String(300), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_type", sa.String(30), nullable=False, server_default="start_of_day"),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tour", "snapshot_date", "snapshot_type", name="uq_golf_snapshot"),
    )


def downgrade():
    op.drop_table("golf_leaderboard_snapshots")
