"""add discover interactions

Revision ID: add_discover_interactions
Revises: add_discover_feed_indexes
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa

revision = "add_discover_interactions"
down_revision = "add_discover_feed_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discover_interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("surface", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("item_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("item_name", sa.String(300), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discover_interactions_user_id", "discover_interactions", ["user_id"])
    op.create_index("ix_discover_interactions_session_id", "discover_interactions", ["session_id"])
    op.create_index("ix_discover_interactions_action", "discover_interactions", ["action"])
    op.create_index("ix_discover_interactions_category", "discover_interactions", ["category"])
    op.create_index("ix_discover_interactions_created_at", "discover_interactions", ["created_at"])
    op.create_index(
        "ix_discover_interactions_rollup",
        "discover_interactions",
        ["created_at", "surface", "category", "action"],
    )
    op.create_index(
        "ix_discover_interactions_item",
        "discover_interactions",
        ["item_type", "item_id", "created_at"],
    )


def downgrade():
    op.drop_table("discover_interactions")
