"""177-A / 178-B: one row per phone for notifications without an account.

MIGRATION-CLASS: merged and run only on Alex's word (177-A: "One new table;
the migration is attended by Alex").

Creates ``push_devices`` (the phone's notification token, its Live Activity
push-to-start token, and its pins) and lets an ``activitykit_registrations``
row be owned by a phone instead of an account: ``user_id`` becomes nullable,
``device_id`` is added, and a check keeps at least one of them set.

``push_devices`` is new and empty, so its GIN indexes build instantly inside the
release phase (gotcha #31 is about big tables). The ``activitykit_registrations``
changes are a nullable column add, a DROP NOT NULL and a CHECK; on a table this
small none of them is a long lock.

Revision ID: push_devices_177a
Revises: open_futures_outcomes_4437
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "push_devices_177a"
down_revision = "open_futures_outcomes_4437"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_devices",
        sa.Column("device_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("apns_env", sa.String(10), nullable=False),
        sa.Column("notification_token", sa.Text(), unique=True),
        sa.Column("la_start_token", sa.Text(), unique=True),
        sa.Column("la_start_token_at", sa.DateTime(timezone=True)),
        sa.Column("os_major", sa.SmallInteger()),
        sa.Column("app_version", sa.String(20)),
        sa.Column(
            "pinned_event_ids",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "pinned_market_ids",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "platform IN ('ios', 'ipados', 'macos', 'appclip')", name="ck_push_devices_platform"
        ),
        sa.CheckConstraint(
            "apns_env IN ('production', 'sandbox')", name="ck_push_devices_apns_env"
        ),
        sa.CheckConstraint(
            "platform <> 'appclip' OR la_start_token IS NULL",
            name="ck_push_devices_appclip_no_la",
        ),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])
    op.create_index(
        "ix_push_devices_pinned_event_ids",
        "push_devices",
        ["pinned_event_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_push_devices_pinned_market_ids",
        "push_devices",
        ["pinned_market_ids"],
        postgresql_using="gin",
    )

    op.add_column(
        "activitykit_registrations",
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("push_devices.device_id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_activitykit_registrations_device_id",
        "activitykit_registrations",
        ["device_id"],
    )
    op.alter_column("activitykit_registrations", "user_id", nullable=True)
    op.create_check_constraint(
        "ck_activitykit_registrations_owner",
        "activitykit_registrations",
        "user_id IS NOT NULL OR device_id IS NOT NULL",
    )


def downgrade():
    # A phone-owned registration has no account to fall back to; it goes.
    op.execute("DELETE FROM activitykit_registrations WHERE user_id IS NULL")
    op.drop_constraint(
        "ck_activitykit_registrations_owner", "activitykit_registrations", type_="check"
    )
    op.alter_column("activitykit_registrations", "user_id", nullable=False)
    op.drop_index(
        "ix_activitykit_registrations_device_id",
        table_name="activitykit_registrations",
    )
    op.drop_column("activitykit_registrations", "device_id")
    op.drop_index("ix_push_devices_pinned_market_ids", table_name="push_devices")
    op.drop_index("ix_push_devices_pinned_event_ids", table_name="push_devices")
    op.drop_index("ix_push_devices_user_id", table_name="push_devices")
    op.drop_table("push_devices")
