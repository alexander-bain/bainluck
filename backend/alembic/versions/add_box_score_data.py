"""Add box_score_data JSONB column to events table.

Stores ESPN box score data for completed games, enabling
expected-vs-actual display on stat prop markets.

Revision ID: add_box_score_data
Revises: rename_gei_to_ei
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = "add_box_score_data"
down_revision = "rename_gei_to_ei"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("box_score_data", JSONB, nullable=True))


def downgrade():
    op.drop_column("events", "box_score_data")
