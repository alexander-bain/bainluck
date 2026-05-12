"""Add bug report lifecycle fields

Revision ID: bug_report_lifecycle
Revises: widen_team_abbrev
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "bug_report_lifecycle"
down_revision = ("widen_team_abbrev", "add_discover_interactions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bug_reports", sa.Column("user_email", sa.String(255), nullable=True))
    op.add_column("bug_reports", sa.Column("backlog_ref", sa.String(20), nullable=True))
    op.add_column("bug_reports", sa.Column("resolution_summary", sa.Text(), nullable=True))
    op.add_column("bug_reports", sa.Column("notification_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bug_reports", "notification_sent_at")
    op.drop_column("bug_reports", "resolution_summary")
    op.drop_column("bug_reports", "backlog_ref")
    op.drop_column("bug_reports", "user_email")
