"""Add client_timing_events (LAT-P232, #2751).

The first-party sink for the felt number. `first_card_ms` is computed in the
browser on every screen arrival today and thrown away for want of a transport;
this table is where it lands instead. Full privacy claim:
`app/utils/client_timing_contract.py`.

Plain btree indexes only — gotcha #31 forbids CREATE INDEX CONCURRENTLY in a
migration (the Heroku release phase times out at ~5 min). The table is empty at
creation, so both indexes build instantly and there is nothing to build
concurrently around.

Revision ID: add_client_timing_events
Revises: uq_event_espn_id
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic. (24 chars — gotcha #1 caps this at 32.)
revision = "add_client_timing_events"
down_revision = "uq_event_espn_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_timing_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_name", sa.String(length=32), nullable=False),
        sa.Column("surface", sa.String(length=64), nullable=True),
        sa.Column("device_class", sa.String(length=64), nullable=True),
        sa.Column("network_class", sa.String(length=64), nullable=True),
        sa.Column("entry", sa.String(length=64), nullable=True),
        sa.Column("outcome_class", sa.String(length=64), nullable=True),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_client_timing_name_time",
        "client_timing_events",
        ["event_name", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_client_timing_created_at",
        "client_timing_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_client_timing_created_at", table_name="client_timing_events")
    op.drop_index("ix_client_timing_name_time", table_name="client_timing_events")
    op.drop_table("client_timing_events")
