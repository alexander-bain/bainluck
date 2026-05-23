"""Add push_preferences JSONB to users

Revision ID: bd72c1098b88
Revises: c7d8e9f0a1b2
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "bd72c1098b88"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("push_preferences", JSONB, server_default="{}", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "push_preferences")
