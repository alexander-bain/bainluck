"""Theme member decisions: one row per (container, member). ADDITIVE ONLY.

#9935 C2 (contract §10.4 S0). Adds one table and one index; the statements live
in ``app/utils/theme_definitions.py`` so the real-Postgres gate
(``tests/integration/test_theme_collections_9935_pg.py``) runs exactly what
this runs.

WHAT THIS DOES, EXHAUSTIVELY.

* ``container_member_decisions`` — the theme assembly's decision ledger: one
  row per ``(container_id, child_type, child_id)`` (``uq_cmd_member``), the
  outcome (CHECK in ('admitted','excluded','withheld')), the closed reason, the
  rule version and its clause-by-clause evidence. ``container_id`` references
  ``containers(id) ON DELETE CASCADE``.
* ``ix_cmd_child`` on ``(child_type, child_id)`` — "every decision about this
  market, in any container".

Nothing is altered or dropped; no existing column changes; no data is written.
The only writer is ``app.tasks.theme_assembly``, which stays behind
``THEME_ASSEMBLY_ENABLED`` (unset) and never publishes a container, so this
migration on its own changes nothing a reader sees.

DEPLOY SAFETY (gotcha #31). The table and its index are created empty, so no
``CONCURRENTLY`` is needed. The foreign key takes a SHARE ROW EXCLUSIVE lock on
``containers`` (declared editions only, tens of rows) for the length of the
release transaction; the alembic lock budget bounds the wait.

MIGRATION-CLASS (D45 / notice 47b): merged only on Alex's word, and no default
fires on silence. The code that writes this ships first and is inert until it
runs (``theme_assembly._schema_gate`` → ``decision_schema_absent``).

Reversible. The D51 undo line, which drops exactly what this adds — and every
decision row written since, with its ``first_decided_at`` and ``attempt_count``
history (``theme_rule`` edges in ``event_edges`` are not touched):

    alembic downgrade serie_a_femminile_sport

Revision ID: ce9935000002
Revises: serie_a_femminile_sport
Create Date: 2026-10-04
"""

from alembic import op

from app.utils.theme_definitions import DOWNGRADE_STATEMENTS, UPGRADE_STATEMENTS

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "ce9935000002"
down_revision = "serie_a_femminile_sport"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
