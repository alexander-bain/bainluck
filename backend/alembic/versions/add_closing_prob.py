"""Add closing line probability columns to events

Revision ID: add_closing_prob
Revises: bug_report_lifecycle
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "add_closing_prob"
down_revision = "bug_report_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("closing_home_probability", sa.Numeric(5, 4), nullable=True))
    op.add_column("events", sa.Column("closing_away_probability", sa.Numeric(5, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "closing_away_probability")
    op.drop_column("events", "closing_home_probability")
