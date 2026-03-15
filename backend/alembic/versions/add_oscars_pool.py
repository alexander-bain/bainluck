"""Add Oscars pool tables for family prediction game.

Revision ID: add_oscars_pool
Revises: add_team_identity
Create Date: 2026-03-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_oscars_pool"
down_revision: Union[str, None] = "add_team_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- 1. Create oscars_pools table --
    op.create_table(
        "oscars_pools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(8), unique=True, nullable=False),
        sa.Column("ceremony_year", sa.Integer(), default=2026),
        sa.Column("created_by_name", sa.String(50), nullable=False),
        sa.Column("picks_locked", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("bonus_markets", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("results", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_oscars_pools_code", "oscars_pools", ["code"])

    # -- 2. Create oscars_pool_members table --
    op.create_table(
        "oscars_pool_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pool_id",
            sa.Integer(),
            sa.ForeignKey("oscars_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(50), nullable=False),
        sa.Column("avatar_emoji", sa.String(10), default="🎬"),
        sa.Column("member_token", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("pool_id", "display_name", name="uq_pool_member_name"),
    )
    op.create_index("ix_oscars_pool_members_pool_id", "oscars_pool_members", ["pool_id"])
    op.create_index("ix_oscars_pool_members_token", "oscars_pool_members", ["member_token"])

    # -- 3. Create oscars_pool_picks table --
    op.create_table(
        "oscars_pool_picks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("oscars_pool_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_key", sa.String(50), nullable=False),
        sa.Column("nominee_name", sa.String(200), nullable=False),
        sa.Column("probability_at_pick", sa.Numeric(7, 6), nullable=False),
        sa.Column("is_confidence_pick", sa.Boolean(), default=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("points_earned", sa.Numeric(8, 2), nullable=True),
        sa.Column("picked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("member_id", "category_key", name="uq_member_category_pick"),
    )
    op.create_index("ix_oscars_pool_picks_member_id", "oscars_pool_picks", ["member_id"])


def downgrade() -> None:
    op.drop_table("oscars_pool_picks")
    op.drop_table("oscars_pool_members")
    op.drop_table("oscars_pools")
