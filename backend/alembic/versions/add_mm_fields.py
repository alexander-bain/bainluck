"""Add March Madness tournament fields to events.

Revision ID: add_mm_fields
Revises: rename_fg_to_mlb
Create Date: 2026-03-05
"""

# revision identifiers
revision = "add_mm_fields"
down_revision = "rename_fg_to_mlb"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("events", sa.Column("tournament_seed_home", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("tournament_seed_away", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("tournament_region", sa.String(30), nullable=True))
    op.add_column("events", sa.Column("tournament_round", sa.String(30), nullable=True))
    op.add_column("events", sa.Column("tournament_type", sa.String(10), nullable=True))
    op.add_column("events", sa.Column("is_tournament_game", sa.Boolean(), server_default="false", nullable=True))


def downgrade():
    op.drop_column("events", "is_tournament_game")
    op.drop_column("events", "tournament_type")
    op.drop_column("events", "tournament_round")
    op.drop_column("events", "tournament_region")
    op.drop_column("events", "tournament_seed_away")
    op.drop_column("events", "tournament_seed_home")
