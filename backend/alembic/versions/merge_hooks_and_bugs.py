"""Merge hook metadata and bug reports branches

Revision ID: merge_hooks_bugs
Revises: c3d4e5f6a7b8, add_bug_reports
Create Date: 2026-05-03
"""
from alembic import op

revision = "merge_hooks_bugs"
down_revision = ("c3d4e5f6a7b8", "add_bug_reports")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
