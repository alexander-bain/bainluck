"""add curation_signals table

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curation_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_platform", sa.String(30)),
        sa.Column("market_ticker", sa.String(200), index=True),
        sa.Column("signal", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("source_device", sa.String(30)),
        sa.Column("processed", sa.Boolean(), server_default="false", index=True),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("futures_markets.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("curation_signals")
