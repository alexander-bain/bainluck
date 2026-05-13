"""Add calibration_probability to futures_outcomes + compound index

Revision ID: add_calibration_prob
Revises: add_closing_prob
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "add_calibration_prob"
down_revision = ("add_closing_prob", "add_pred_challenges")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("futures_outcomes",
        sa.Column("calibration_probability", sa.Numeric(7, 6), nullable=True))
    op.create_index("idx_fos_outcome_captured", "futures_odds_snapshots",
        ["outcome_id", "captured_at"])


def downgrade() -> None:
    op.drop_index("idx_fos_outcome_captured", "futures_odds_snapshots")
    op.drop_column("futures_outcomes", "calibration_probability")
