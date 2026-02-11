"""Add roster_players JSONB column to teams table.

Revision ID: add_roster_players
Revises: add_market_tier
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "add_roster_players"
down_revision = "add_auth_personalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("roster_players", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "roster_players")
