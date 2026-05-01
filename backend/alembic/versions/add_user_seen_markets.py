"""add user_seen_markets table

Revision ID: add_user_seen_mkts
Revises: widen_team_abbrev
"""
from alembic import op
import sqlalchemy as sa

revision = "add_user_seen_mkts"
down_revision = "ba4924b27a0c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_seen_markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("session_id", sa.String(100), nullable=True, index=True),
        sa.Column("item_type", sa.String(10), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("user_seen_markets")
