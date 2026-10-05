"""Bound activity credential authorization, source only; legacy null fails closed.
Revision ID: activitykit_credential_expiry
Revises: activitykit_delivery
"""

from alembic import op
import sqlalchemy as sa

revision = "activitykit_credential_expiry"
down_revision = "activitykit_delivery"
branch_labels = None
depends_on = None


def upgrade():
    # Do not backfill from updated_at: token rotations would renew authorization.
    op.add_column(
        "activitykit_registrations", sa.Column("created_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "activitykit_registrations", sa.Column("expires_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_activitykit_registrations_expires_at",
        "activitykit_registrations",
        ["expires_at"],
    )


def downgrade():
    op.drop_index(
        "ix_activitykit_registrations_expires_at",
        table_name="activitykit_registrations",
    )
    op.drop_column("activitykit_registrations", "expires_at")
    op.drop_column("activitykit_registrations", "created_at")
