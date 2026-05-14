"""Add Discover review decision log

Revision ID: discover_review_decisions
Revises: add_calibration_prob
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "discover_review_decisions"
down_revision = "add_calibration_prob"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discover_review_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("item_id", sa.String(length=100), nullable=False),
        sa.Column("item_name", sa.String(length=300), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("surface", sa.String(length=20), nullable=True),
        sa.Column("auth_segment", sa.String(length=20), nullable=True),
        sa.Column("family_key", sa.String(length=300), nullable=True),
        sa.Column("archetype", sa.String(length=80), nullable=True),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_discover_review_decisions_category",
        "discover_review_decisions",
        ["category"],
    )
    op.create_index(
        "ix_discover_review_decisions_created_at",
        "discover_review_decisions",
        ["created_at"],
    )
    op.create_index(
        "ix_discover_review_decisions_decision",
        "discover_review_decisions",
        ["decision"],
    )
    op.create_index(
        "ix_discover_review_decisions_item",
        "discover_review_decisions",
        ["item_type", "item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_discover_review_decisions_item", table_name="discover_review_decisions")
    op.drop_index("ix_discover_review_decisions_decision", table_name="discover_review_decisions")
    op.drop_index("ix_discover_review_decisions_created_at", table_name="discover_review_decisions")
    op.drop_index("ix_discover_review_decisions_category", table_name="discover_review_decisions")
    op.drop_table("discover_review_decisions")
