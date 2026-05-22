"""add featured_market_captures table

Revision ID: c3f8a1b2d4e5
Revises: abfa60dd064c
Create Date: 2026-05-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "c3f8a1b2d4e5"
down_revision: Union[str, None] = "abfa60dd064c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "featured_market_captures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False, index=True),
        sa.Column("captured_date", sa.String(10), nullable=False, index=True),
        sa.Column("market_name", sa.String(500), nullable=False),
        sa.Column("external_id", sa.String(200), index=True),
        sa.Column(
            "matched_market_id",
            sa.Integer(),
            sa.ForeignKey("futures_markets.id"),
            index=True,
        ),
        sa.Column("category", sa.String(100), index=True),
        sa.Column("url", sa.Text()),
        sa.Column("rank", sa.Integer()),
        sa.Column("volume_24h", sa.Numeric()),
        sa.Column("probability", sa.Numeric()),
        sa.Column("extra", JSONB()),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            index=True,
        ),
        sa.UniqueConstraint(
            "source",
            "captured_date",
            "external_id",
            name="uq_featured_capture_source_date_ext",
        ),
    )
    op.create_index(
        "ix_featured_capture_source_date",
        "featured_market_captures",
        ["source", "captured_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_featured_capture_source_date",
        table_name="featured_market_captures",
    )
    op.drop_table("featured_market_captures")
