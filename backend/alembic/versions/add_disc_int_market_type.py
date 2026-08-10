"""Add market_type to discover_interactions (Queue 310).

Records the canonical market shape (claim | quantity | duel | field |
container_member | unshaped) at interaction time, so Discover engagement can be
sliced by shape in the export_engagement rollup — i.e. so "do quantity ladders
out-tap fields?" is answerable as a RATE, not just a tap count.

Nullable with no backfill: rows written before this column existed did not
capture the signal, and NULL means "not recorded", never "unshaped".

Revision ID: add_disc_int_market_type
Revises: add_durable_state_snaps
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "add_disc_int_market_type"
down_revision = "add_durable_state_snaps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discover_interactions",
        sa.Column("market_type", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discover_interactions", "market_type")
