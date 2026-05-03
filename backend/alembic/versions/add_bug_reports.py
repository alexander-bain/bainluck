"""Add bug_reports table for rage shake feature.

Revision ID: add_bug_reports
Revises: f1a2b3c4d5e6
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "add_bug_reports"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bug_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True, index=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("screenshot_base64", sa.Text, nullable=True),
        sa.Column("app_state", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="new", index=True),
        sa.Column("admin_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("bug_reports")
