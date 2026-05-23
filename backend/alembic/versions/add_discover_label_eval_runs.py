"""add discover label eval runs

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b6c7d8e9f0a1"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "discover_label_eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column(
            "eval_name",
            sa.String(80),
            nullable=False,
            server_default="discover_label_gold_set",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("input_source", sa.Text(), nullable=True),
        sa.Column("dataset_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dataset_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("surface", sa.String(50), nullable=True),
        sa.Column("reviewer", sa.String(100), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tapworthy_at_k", sa.Float(), nullable=True),
        sa.Column("boring_rate_at_k", sa.Float(), nullable=True),
        sa.Column("duplicate_family_rate_at_k", sa.Float(), nullable=True),
        sa.Column("unclear_rate_at_k", sa.Float(), nullable=True),
        sa.Column("bad_explanation_rate_at_k", sa.Float(), nullable=True),
        sa.Column("bad_image_rate_at_k", sa.Float(), nullable=True),
        sa.Column("broad_appeal_at_k", sa.Float(), nullable=True),
        sa.Column("fixable_interest_rate_at_k", sa.Float(), nullable=True),
        sa.Column("tapworthy_recall_at_k", sa.Float(), nullable=True),
        sa.Column("metric_summary", JSONB, nullable=False, server_default="{}"),
        sa.Column("category_breakdowns", JSONB, nullable=False, server_default="{}"),
        sa.Column("notable_regressions", JSONB, nullable=False, server_default="[]"),
        sa.Column("eval_metadata", JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discover_label_eval_runs_run_id", "discover_label_eval_runs", ["run_id"], unique=True)
    op.create_index("ix_discover_label_eval_runs_status", "discover_label_eval_runs", ["status"])
    op.create_index("ix_discover_label_eval_runs_captured_at", "discover_label_eval_runs", ["captured_at"])
    op.create_index("ix_discover_label_eval_name_captured", "discover_label_eval_runs", ["eval_name", "captured_at"])
    op.create_index("ix_discover_label_eval_status_captured", "discover_label_eval_runs", ["status", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_discover_label_eval_status_captured", table_name="discover_label_eval_runs")
    op.drop_index("ix_discover_label_eval_name_captured", table_name="discover_label_eval_runs")
    op.drop_index("ix_discover_label_eval_runs_captured_at", table_name="discover_label_eval_runs")
    op.drop_index("ix_discover_label_eval_runs_status", table_name="discover_label_eval_runs")
    op.drop_index("ix_discover_label_eval_runs_run_id", table_name="discover_label_eval_runs")
    op.drop_table("discover_label_eval_runs")
