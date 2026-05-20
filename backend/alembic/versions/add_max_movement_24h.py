"""Add max_movement_24h to futures_markets + composite index on futures_odds_snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "add_max_movement_24h"
down_revision = "add_curator_gt_items"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "futures_markets",
        sa.Column("max_movement_24h", sa.Numeric(7, 4), nullable=True),
    )
    op.create_index(
        "ix_fos_outcome_bookmaker",
        "futures_odds_snapshots",
        ["outcome_id", "bookmaker"],
    )


def downgrade():
    op.drop_index("ix_fos_outcome_bookmaker", "futures_odds_snapshots")
    op.drop_column("futures_markets", "max_movement_24h")
