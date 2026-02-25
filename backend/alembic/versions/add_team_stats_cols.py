"""Add standings and season stats columns to teams

Revision ID: add_team_stats_cols
Revises: nullable_external_id
Create Date: 2026-02-25
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "add_team_stats_cols"
down_revision = "nullable_external_id"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("standings_data", JSONB, nullable=True))
    op.add_column("teams", sa.Column("standings_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("teams", sa.Column("season_stats", JSONB, nullable=True))
    op.add_column("teams", sa.Column("season_stats_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "season_stats_updated_at")
    op.drop_column("teams", "season_stats")
    op.drop_column("teams", "standings_updated_at")
    op.drop_column("teams", "standings_data")
