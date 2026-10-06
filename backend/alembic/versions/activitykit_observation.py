"""Persist canonical observations. SOURCE ONLY: attended application required."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "activitykit_observation"
down_revision = "activitykit_credential_expiry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activitykit_observations",
        sa.Column(
            "event_id", sa.Integer(), sa.ForeignKey("events.id"), primary_key=True
        ),
        sa.Column("sequence", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_activitykit_observation_sequence"),
    )


def downgrade():
    op.drop_table("activitykit_observations")
