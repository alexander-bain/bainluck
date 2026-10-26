"""A single durable DNPL ordering domain; no existing event/data scan.

PILLAR: TRUTH. SHIP: new readers can safely resume fast probabilities after
Redis authority loss. This only creates a disabled seed; it activates nothing.
There is no FK/event lock. Runtime cannot recreate a deleted row. Never downgrade
after an incarnation has been allocated: dropping its history permits reuse.
An application rollback leaves this tiny table in place and serves committed
updates. Activation and production migration remain Integrator-owned gates.
"""

from alembic import op
import sqlalchemy as sa

revision = "dnpl_authority_10090"
down_revision = "owed_chart_points_11181"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dnpl_authority",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("protocol", sa.SmallInteger(), nullable=False),
        sa.Column("incarnation", sa.BigInteger(), nullable=False),
        sa.Column("namespace", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(9), nullable=False),
        sa.Column("redis_run_id", sa.String(40), nullable=False),
        sa.Column("redis_master_replid", sa.String(40), nullable=False),
        sa.Column("policy_fingerprint", sa.String(128), nullable=False),
        sa.CheckConstraint("id = 1 AND protocol = 3", name="dnpl_authority_singleton"),
        sa.CheckConstraint(
            "incarnation BETWEEN 0 AND 9007199254740991", name="dnpl_authority_range"
        ),
        sa.CheckConstraint(
            "state IN ('preparing', 'ready', 'disabled')", name="dnpl_authority_state"
        ),
        sa.CheckConstraint(
            "(incarnation = 0 AND state = 'disabled' AND "
            "namespace = '00000000-0000-0000-0000-000000000000'::uuid AND "
            "operation_id = '00000000-0000-0000-0000-000000000000'::uuid AND "
            "redis_run_id = '' AND redis_master_replid = '' AND policy_fingerprint = '') OR "
            "(incarnation > 0 AND namespace <> '00000000-0000-0000-0000-000000000000'::uuid AND "
            "operation_id <> '00000000-0000-0000-0000-000000000000'::uuid AND "
            "redis_run_id ~ '^[0-9a-f]{40}$' AND redis_master_replid ~ '^[0-9a-f]{40}$' AND "
            "length(policy_fingerprint) BETWEEN 1 AND 128)",
            name="dnpl_authority_identity",
        ),
    )
    op.execute(
        "INSERT INTO dnpl_authority VALUES "
        "(1, 3, 0, '00000000-0000-0000-0000-000000000000', "
        "'00000000-0000-0000-0000-000000000000', 'disabled', '', '', '')"
    )


def downgrade():
    # A migration downgrade must never erase issued identities, even when the
    # application has been rolled back. Keep this an explicit manual decision.
    raise RuntimeError("DNPL authority history must be retained; roll back code only")
