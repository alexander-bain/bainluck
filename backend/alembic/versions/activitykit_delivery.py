"""Persist ActivityKit reservations without retaining credentials.
Revision ID: activitykit_delivery
Revises: activitykit_registration
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "activitykit_delivery"
down_revision = "activitykit_registration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activitykit_deliveries",
        sa.Column(
            "activity_id",
            sa.String(128),
            sa.ForeignKey("activitykit_registrations.activity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("registration_version", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("lease_id", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("activitykit_deliveries")
