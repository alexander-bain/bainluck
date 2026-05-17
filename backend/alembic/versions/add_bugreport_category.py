"""Add category to bug_reports

Revision ID: add_bugreport_cat
Revises: discover_review_decisions
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "add_bugreport_cat"
down_revision = "discover_review_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bug_reports", sa.Column("category", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("bug_reports", "category")
