"""add ranking_judgments table

Revision ID: f7e8d9c0b1a2
Revises: a1b2c3d4e5f6
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "f7e8d9c0b1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "ranking_judgments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), server_default=sa.func.current_date()),
        sa.Column("surface", sa.String(50), nullable=False, server_default="discover"),
        sa.Column("rank_seen", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.String(20), nullable=False, server_default="futures"),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("futures_markets.id"), nullable=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("market_name", sa.Text(), nullable=True),
        sa.Column("label", sa.String(10), nullable=False),
        sa.Column("reason_tags", ARRAY(sa.String()), server_default="{}"),
        sa.Column("better_than", sa.Text(), nullable=True),
        sa.Column("worse_than", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("score_at_review", sa.Float(), nullable=True),
        sa.Column("category_at_review", sa.String(100), nullable=True),
        sa.Column("archetype_at_review", sa.String(100), nullable=True),
        sa.Column("quality_class_at_review", sa.String(50), nullable=True),
        sa.Column("headline_at_review", sa.Text(), nullable=True),
        sa.Column("feed_request_id", sa.String(100), nullable=True),
        sa.Column("reviewer", sa.String(100), nullable=False, server_default="alex"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ranking_judgments")
