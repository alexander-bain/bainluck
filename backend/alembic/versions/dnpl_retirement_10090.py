"""Retain one exact old namespace until bounded cleanup is acknowledged.

TRUTH: safe fast-update recovery cannot forget a namespace after a crash.
No existing event scan, activation, Redis access or namespace deletion here.
This is a single optional record, not a growing history or work queue.
"""

from alembic import op

revision = "dnpl_retirement_10090"
down_revision = "dnpl_authority_10090"
branch_labels = None
depends_on = None


def upgrade():
    # Identical field types/identity constraints; no copy of the seed/data.
    op.execute(
        "CREATE TABLE dnpl_namespace_retirement "
        "(LIKE dnpl_authority INCLUDING CONSTRAINTS INCLUDING INDEXES)"
    )
    op.execute(
        "ALTER TABLE dnpl_namespace_retirement ADD CONSTRAINT "
        "dnpl_retirement_allocated CHECK (incarnation > 0)"
    )

    op.execute(
        "ALTER TABLE dnpl_authority ADD COLUMN activation_step SMALLINT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE dnpl_authority ADD CONSTRAINT dnpl_activation_step CHECK (activation_step BETWEEN 0 AND 2)"
    )


def downgrade():
    raise RuntimeError("DNPL retirement evidence must be retained; roll back code only")
