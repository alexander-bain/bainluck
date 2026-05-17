"""Add device_tokens table for push notifications

Revision ID: add_device_tokens
Revises: add_bugreport_cat
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "add_device_tokens"
down_revision = "add_bugreport_cat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_token", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("device_token", name="uq_device_tokens_token"),
    )
    op.create_index("ix_device_tokens_device_token", "device_tokens", ["device_token"])
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])
    op.create_index("ix_device_tokens_session_id", "device_tokens", ["session_id"])


def downgrade() -> None:
    op.drop_table("device_tokens")
