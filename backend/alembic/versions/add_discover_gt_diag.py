"""Add Discover ground truth diagnostic snapshots

Revision ID: add_discover_gt_diag
Revises: add_device_tokens
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_discover_gt_diag"
down_revision = "add_device_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discover_ground_truth_diagnostics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_group", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("item_name", sa.String(length=500), nullable=False),
        sa.Column("feed_name", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("probability", sa.String(length=250), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.String(length=50), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("quality_class", sa.String(length=40), nullable=True),
        sa.Column("archetype", sa.String(length=80), nullable=True),
        sa.Column("family_key", sa.String(length=300), nullable=True),
        sa.Column("story_key", sa.String(length=300), nullable=True),
        sa.Column("triage_bucket", sa.String(length=80), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("matched_market_id", sa.Integer(), nullable=True),
        sa.Column("trace_status", sa.String(length=80), nullable=True),
        sa.Column("trace_summary", sa.Text(), nullable=True),
        sa.Column("db_match_count", sa.Integer(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_run_id",
        "discover_ground_truth_diagnostics",
        ["run_id"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_source_group",
        "discover_ground_truth_diagnostics",
        ["source_group"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_status",
        "discover_ground_truth_diagnostics",
        ["status"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_category",
        "discover_ground_truth_diagnostics",
        ["category"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_triage_bucket",
        "discover_ground_truth_diagnostics",
        ["triage_bucket"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_matched_market_id",
        "discover_ground_truth_diagnostics",
        ["matched_market_id"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_trace_status",
        "discover_ground_truth_diagnostics",
        ["trace_status"],
    )
    op.create_index(
        "ix_discover_ground_truth_diagnostics_captured_at",
        "discover_ground_truth_diagnostics",
        ["captured_at"],
    )
    op.create_index(
        "ix_discover_gt_diag_run_group",
        "discover_ground_truth_diagnostics",
        ["run_id", "source_group", "status"],
    )
    op.create_index(
        "ix_discover_gt_diag_captured",
        "discover_ground_truth_diagnostics",
        ["captured_at", "source_group", "triage_bucket"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discover_gt_diag_captured",
        table_name="discover_ground_truth_diagnostics",
    )
    op.drop_index(
        "ix_discover_gt_diag_run_group",
        table_name="discover_ground_truth_diagnostics",
    )
    op.drop_table("discover_ground_truth_diagnostics")
