"""Add prediction_challenges table for friend challenges

Revision ID: add_pred_challenges
Revises: add_closing_prob
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "add_pred_challenges"
down_revision = "add_closing_prob"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_challenges",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("creator_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("creator_session_id", sa.String(100), nullable=True),
        sa.Column("challenge_code", sa.String(20), nullable=False, unique=True, index=True),
        sa.Column("market_id", sa.Integer, sa.ForeignKey("futures_markets.id"), nullable=False),
        sa.Column("market_name", sa.Text, nullable=True),
        sa.Column("creator_guess", sa.String(10), nullable=False),
        sa.Column("creator_threshold", sa.Integer, nullable=False),
        sa.Column("friend_guess", sa.String(10), nullable=True),
        sa.Column("friend_session_id", sa.String(100), nullable=True),
        sa.Column("actual_probability", sa.Numeric, nullable=True),
        sa.Column("creator_correct", sa.Boolean, nullable=True),
        sa.Column("friend_correct", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("prediction_challenges")
