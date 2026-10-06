"""Signed-in ActivityKit registration ownership and tombstones.

Revision ID: activitykit_registration
Revises: prob_publications
"""

from alembic import op
import sqlalchemy as sa

revision = "activitykit_registration"
down_revision = "prob_publications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activitykit_registrations",
        sa.Column("activity_id", sa.String(128), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("push_token", sa.Text()),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("mutation_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_activitykit_registrations_user_id", "activitykit_registrations", ["user_id"]
    )
    op.create_index(
        "ix_activitykit_registrations_event_id",
        "activitykit_registrations",
        ["event_id"],
    )


def downgrade():
    op.drop_table("activitykit_registrations")
