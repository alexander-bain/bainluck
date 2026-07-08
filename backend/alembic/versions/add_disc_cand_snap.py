"""Add Discover pre-ranking candidate-pool snapshots (#142/RANK-2)

Revision ID: add_disc_cand_snap
Revises: d596features01
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_disc_cand_snap"
down_revision = "d596features01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discover_candidate_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column(
            "item_type",
            sa.String(length=20),
            nullable=False,
            server_default="futures",
        ),
        sa.Column("served_rank", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("quality_class", sa.String(length=40), nullable=True),
        sa.Column("family_key", sa.String(length=300), nullable=True),
        sa.Column("story_key", sa.String(length=300), nullable=True),
        sa.Column("rank_score", sa.Float(), nullable=True),
        sa.Column("display_score", sa.Integer(), nullable=True),
        sa.Column("pre_blend_rank_score", sa.Float(), nullable=True),
        sa.Column("category_base", sa.Float(), nullable=True),
        sa.Column("interestingness_score", sa.Float(), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("anatomy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_discover_candidate_snapshots_run_id",
        "discover_candidate_snapshots",
        ["run_id"],
    )
    op.create_index(
        "ix_discover_candidate_snapshots_market_id",
        "discover_candidate_snapshots",
        ["market_id"],
    )
    op.create_index(
        "ix_discover_candidate_snapshots_served_rank",
        "discover_candidate_snapshots",
        ["served_rank"],
    )
    op.create_index(
        "ix_discover_candidate_snapshots_category",
        "discover_candidate_snapshots",
        ["category"],
    )
    op.create_index(
        "ix_discover_candidate_snapshots_captured_at",
        "discover_candidate_snapshots",
        ["captured_at"],
    )
    op.create_index(
        "ix_discover_candidate_snap_run",
        "discover_candidate_snapshots",
        ["run_id", "served_rank"],
    )
    op.create_index(
        "ix_discover_candidate_snap_captured",
        "discover_candidate_snapshots",
        ["captured_at", "market_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discover_candidate_snap_captured",
        table_name="discover_candidate_snapshots",
    )
    op.drop_index(
        "ix_discover_candidate_snap_run",
        table_name="discover_candidate_snapshots",
    )
    op.drop_index(
        "ix_discover_candidate_snapshots_captured_at",
        table_name="discover_candidate_snapshots",
    )
    op.drop_index(
        "ix_discover_candidate_snapshots_category",
        table_name="discover_candidate_snapshots",
    )
    op.drop_index(
        "ix_discover_candidate_snapshots_served_rank",
        table_name="discover_candidate_snapshots",
    )
    op.drop_index(
        "ix_discover_candidate_snapshots_market_id",
        table_name="discover_candidate_snapshots",
    )
    op.drop_index(
        "ix_discover_candidate_snapshots_run_id",
        table_name="discover_candidate_snapshots",
    )
    op.drop_table("discover_candidate_snapshots")
