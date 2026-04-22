"""Add completed_at to events

Revision ID: add_completed_at
Revises: add_golf_lb_snap
"""
from alembic import op
import sqlalchemy as sa

revision = "add_completed_at"
down_revision = "add_golf_lb_snap"


def upgrade():
    op.add_column("events", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("events", "completed_at")
