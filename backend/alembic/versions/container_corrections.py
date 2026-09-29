"""Container corrections: a withdrawn member stays withdrawn. ADDITIVE ONLY.

#9651 (canonical v3 #9217), the narrow #5344 contract. Adds one table and two
columns; the statements live in ``app/utils/container_corrections.py`` so the
real-Postgres gates run exactly what this runs.

WHAT THIS DOES, EXHAUSTIVELY.

* ``containers.publication_state`` VARCHAR(16) NOT NULL DEFAULT 'unpublished',
  CHECK in ('unpublished','published','withdrawn'). Every existing container
  reads ``unpublished``: nothing becomes reader-visible by this migration.
* ``containers.membership_revision`` INTEGER NOT NULL DEFAULT 0.
* ``container_corrections`` — an append-only decision ledger (member
  withdraw/readmit, publication publish/withdraw) with an index on
  ``(container_id, scope, child_type, child_id, id)``.

Nothing is altered or dropped; no existing column changes; no data is written.

DEPLOY SAFETY (gotcha #31). ``ADD COLUMN ... NOT NULL DEFAULT <constant>`` is a
catalogue-only change on Postgres 11+; the inline CHECK validates against the
``containers`` table, which holds declared editions only (tens of rows). The new
table and its index are created empty. No ``CONCURRENTLY`` is needed.

MIGRATION-CLASS (D45 / notice 47b): merged only on Alex's word, and no default
fires on silence. The code that reads this ships first and is inert until it
runs (``correction_schema_present``).

Reversible. The D51 undo line, which drops exactly what this adds:

    alembic downgrade wps_rev_trigger

Revision ID: container_corrections
Revises: wps_rev_trigger
Create Date: 2026-09-29
"""

from alembic import op

from app.utils.container_corrections import DOWNGRADE_STATEMENTS, UPGRADE_STATEMENTS

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "container_corrections"
down_revision = "wps_rev_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
