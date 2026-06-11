"""Add features JSONB column to discover_review_decisions.

Revision ID: d596features01
Revises: c852a0story01
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d596features01"
down_revision = "c852a0story01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "discover_review_decisions",
        sa.Column("features", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("discover_review_decisions", "features")
