"""Add hook generation metadata to futures_markets

Revision ID: c3d4e5f6a7b8
Revises: a7b8c9d0e1f2
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("futures_markets", sa.Column("hook_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("futures_markets", sa.Column("hook_leader_at_generation", sa.String(200), nullable=True))
    op.alter_column("futures_markets", "hook_description", type_=sa.String(500), existing_type=sa.String(300))


def downgrade():
    op.alter_column("futures_markets", "hook_description", type_=sa.String(300), existing_type=sa.String(500))
    op.drop_column("futures_markets", "hook_leader_at_generation")
    op.drop_column("futures_markets", "hook_generated_at")
