"""Widen teams.abbreviation from VARCHAR(10) to VARCHAR(20).

College team abbreviations like "STONY BROOK" exceed 10 chars.

Revision ID: widen_team_abbrev
Revises: add_matching_overrides
Create Date: 2026-03-27
"""

revision = "widen_team_abbrev"
down_revision = "add_matching_overrides"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column("teams", "abbreviation",
                    type_=sa.String(20),
                    existing_type=sa.String(10))


def downgrade():
    op.alter_column("teams", "abbreviation",
                    type_=sa.String(10),
                    existing_type=sa.String(20))
