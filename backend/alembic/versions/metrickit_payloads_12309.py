"""#12309: a table for Apple MetricKit diagnostics forwarded by consenting phones.

THE SHIP. Hangs, slow launches and the crashes Crashlytics never sees reach us
as Apple's own call stacks, so a fix starts from a stack rather than a guess.

WHAT THIS DOES, EXHAUSTIVELY.

* Creates one new, empty table ``metrickit_payloads``: one row per MetricKit
  diagnostic (crash, hang, CPU or disk-write exception, slow launch) or per
  day's metrics, with the version and device fields copied from the payload's
  own metadata. No user, session, IP or cookie column, and no foreign key.
* Creates two plain b-tree indexes on it: ``(kind, received_at)`` for the reads
  and ``received_at`` for the retention sweep. Both are built on an EMPTY
  table, so gotcha #31 has nothing to apply to.

No existing table, column or index changes. ``POST /api/telemetry/metrickit``
(``app.routes.metrickit``) is the only writer; the phone sends only for a reader
who granted telemetry consent.

MIGRATION-CLASS (D45): merges on Alex's word.

Reversible. The undo line is

    alembic downgrade open_futures_outcomes_4437

which drops the table and its two indexes. Until the app build that sends ships,
the table is empty; after it, the rows are diagnostics with a 30-day life.

Revision ID: metrickit_payloads_12309
Revises: open_futures_outcomes_4437
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters (this one is 24).
revision = "metrickit_payloads_12309"
down_revision = "open_futures_outcomes_4437"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metrickit_payloads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("app_version", sa.String(64), nullable=True),
        sa.Column("app_build", sa.String(64), nullable=True),
        sa.Column("os_version", sa.String(64), nullable=True),
        sa.Column("device_type", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metrickit_kind_time", "metrickit_payloads", ["kind", "received_at"])
    op.create_index("ix_metrickit_received_at", "metrickit_payloads", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_metrickit_received_at", table_name="metrickit_payloads")
    op.drop_index("ix_metrickit_kind_time", table_name="metrickit_payloads")
    op.drop_table("metrickit_payloads")
