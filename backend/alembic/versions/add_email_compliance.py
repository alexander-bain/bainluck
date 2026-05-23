"""Add email compliance columns to users

Revision ID: e2f3a4b5c6d7
Revises: f7e8d9c0b1a2
Create Date: 2026-05-23

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e2f3a4b5c6d7"
down_revision = "f7e8d9c0b1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "unsubscribe_token",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_users_unsubscribe_token",
        "users",
        ["unsubscribe_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_unsubscribe_token", table_name="users")
    op.drop_column("users", "unsubscribe_token")
    op.drop_column("users", "email_preferences")
