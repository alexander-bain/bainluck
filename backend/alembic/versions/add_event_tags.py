"""Add event_tags JSONB column with GIN index to events table.

Stores deterministic taxonomy tags as a flat namespaced array,
e.g. ["sport:basketball", "tier:1", "status:live", "signal:upset"].
Queryable via GIN containment: WHERE event_tags @> '["tier:1"]'

Revision ID: add_event_tags
Revises: add_box_score_data
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = "add_event_tags"
down_revision = "add_box_score_data"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "events",
        sa.Column("event_tags", JSONB, server_default="[]", nullable=True),
    )
    op.create_index(
        "ix_events_event_tags",
        "events",
        ["event_tags"],
        postgresql_using="gin",
        postgresql_ops={"event_tags": "jsonb_path_ops"},
    )


def downgrade():
    op.drop_index("ix_events_event_tags", table_name="events")
    op.drop_column("events", "event_tags")
