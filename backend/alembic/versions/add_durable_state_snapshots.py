"""Queue 298 (#1512) — durable_state_snapshots: last-good state that outlives Redis

Calibration's "durable" last-good and all seven sentinel scorecards lived in the
same 50MB allkeys-lru Redis, so eviction blanked the public page and left the
/last rails saying no_run_cached hours after a healthy beat. This is the one
narrow cross-process substrate they publish to BEFORE the volatile copy.

One row per artifact identity (not a history table) — replaced atomically under
a generation guard so a stale writer can never overwrite a newer good copy.

Plain index creation (no CREATE INDEX CONCURRENTLY, gotcha #31) — the table
starts empty so index builds are instant.

Revision ID: add_durable_state_snaps
Revises: add_game_moments
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_durable_state_snaps"
down_revision = "add_game_moments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "durable_state_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.String(length=60), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "source", sa.String(length=80), nullable=False, server_default="unknown"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # UNIQUE is load-bearing, not hygiene: it is the ON CONFLICT target the
    # atomic generation-guarded replace depends on.
    op.create_index(
        "ix_durable_state_snapshots_identity",
        "durable_state_snapshots",
        ["identity"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_durable_state_snapshots_identity", table_name="durable_state_snapshots"
    )
    op.drop_table("durable_state_snapshots")
