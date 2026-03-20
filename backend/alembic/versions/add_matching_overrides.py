"""Add matching_overrides table for admin-curated grid matching decisions.

Revision ID: add_matching_overrides
Revises: rename_gei_to_ei
Create Date: 2026-03-19
"""

revision = "add_matching_overrides"
down_revision = "add_scoring_plays"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.create_table(
        "matching_overrides",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_slug", sa.String(50), nullable=False, index=True),
        sa.Column("override_type", sa.String(50), nullable=False),
        sa.Column("source_name", sa.String(300), nullable=False),
        sa.Column("target_name", sa.String(300), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False, server_default="approved"),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("league_slug", "override_type", "source_name", name="uq_override_key"),
    )


def downgrade():
    op.drop_table("matching_overrides")
