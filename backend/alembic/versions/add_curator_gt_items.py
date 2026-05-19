"""Add reviewed external curator ground truth items

Revision ID: add_curator_gt_items
Revises: add_closing_spread_total
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_curator_gt_items"
down_revision = "add_closing_spread_total"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_curator_ground_truth_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("probability", sa.String(length=250), nullable=True),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.String(length=50), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=True),
        sa.Column("handle", sa.String(length=100), nullable=True),
        sa.Column("engagement", sa.String(length=100), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("extraction_notes", sa.Text(), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=20),
            nullable=False,
            server_default="accepted",
        ),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_external_curator_gt_dedupe_key"),
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_source",
        "external_curator_ground_truth_items",
        ["source"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_category",
        "external_curator_ground_truth_items",
        ["category"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_platform",
        "external_curator_ground_truth_items",
        ["platform"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_handle",
        "external_curator_ground_truth_items",
        ["handle"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_confidence",
        "external_curator_ground_truth_items",
        ["confidence"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_review_status",
        "external_curator_ground_truth_items",
        ["review_status"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_imported_at",
        "external_curator_ground_truth_items",
        ["imported_at"],
    )
    op.create_index(
        "ix_external_curator_ground_truth_items_updated_at",
        "external_curator_ground_truth_items",
        ["updated_at"],
    )
    op.create_index(
        "ix_external_curator_gt_source_date",
        "external_curator_ground_truth_items",
        ["source", "published_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_curator_gt_source_date",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_updated_at",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_imported_at",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_review_status",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_confidence",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_handle",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_platform",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_category",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_index(
        "ix_external_curator_ground_truth_items_source",
        table_name="external_curator_ground_truth_items",
    )
    op.drop_table("external_curator_ground_truth_items")
