"""Add closing spread and total line columns to events

Revision ID: add_closing_spread_total
Revises: add_discover_gt_diag
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_closing_spread_total"
down_revision = "add_discover_gt_diag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("closing_home_spread", sa.Numeric(4, 1), nullable=True))
    op.add_column("events", sa.Column("closing_home_spread_odds", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("closing_away_spread_odds", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("closing_over_under", sa.Numeric(5, 1), nullable=True))
    op.add_column("events", sa.Column("closing_over_odds", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("closing_under_odds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "closing_under_odds")
    op.drop_column("events", "closing_over_odds")
    op.drop_column("events", "closing_over_under")
    op.drop_column("events", "closing_away_spread_odds")
    op.drop_column("events", "closing_home_spread_odds")
    op.drop_column("events", "closing_home_spread")
