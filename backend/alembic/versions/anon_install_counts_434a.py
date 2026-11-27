"""#13261 / 434-A: create anonymous_install_counts daily counter table.

MIGRATION-CLASS: waits for Alex's explicit "go" in his window; not executed
before merge authorization.

Creates ``anonymous_install_counts``, a brand-new empty daily aggregate counter
table keyed by ``(day, app_version, event)`` for the three pre-consent lifecycle
counts (``first_open``, ``first_run_finished``, ``previous_session_crashed``).
Zero per-event rows, zero IPs, and zero user/device/install identifiers.

Revision ID: anon_install_counts_434a
Revises: retired_team_redirects_13229
"""

import sqlalchemy as sa
from alembic import op

revision = "anon_install_counts_434a"
down_revision = "retired_team_redirects_13229"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anonymous_install_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("app_version", sa.String(16), nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "app_version", "event"),
        sa.CheckConstraint(
            "event IN ('first_open', 'first_run_finished', 'previous_session_crashed')",
            name="ck_anon_install_counts_event",
        ),
        sa.CheckConstraint(
            "count >= 0",
            name="ck_anon_install_counts_count_nonneg",
        ),
    )


def downgrade():
    op.drop_table("anonymous_install_counts")
