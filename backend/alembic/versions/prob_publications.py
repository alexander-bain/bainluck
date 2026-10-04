"""#4971: `probability_publications`, one row per committed nonvenue publication. ADDITIVE ONLY.

THE SHIP. Chart history and the published live probability tell the same
recorded story. From the moment recording is switched on, each committed bag a
betting / stat_model / mlb / espn writer published is kept exactly, with its
blend and the producer's evidence, instead of being reconstructed later from a
mutable book population. The contract is the docstring of
`app/utils/probability_publication.py`.

WHAT THIS DOES, EXHAUSTIVELY:

* Creates the empty table `probability_publications` (columns as
  `app.models.models.ProbabilityPublication`) with its bigserial primary key and
  the unique constraint `uq_probability_publications_event_rev` on
  `(event_id, rev)`. That constraint's index is the only index, and it serves
  "this event's publications in order".

Nothing is altered or dropped. No existing column changes. No data is written.
There is no foreign key to `events`, so the migration takes no lock on
`events`, and a publication record outlives a drained duplicate row.

THE WRITER IS DARK. `nonvenue_live_push._before_commit` records only while
`PROBABILITY_PUBLICATION_RECORDING=true`, and that var is unset. On its own,
this migration changes nothing a reader sees or a task does.

DEPLOY SAFETY (gotcha #31). The table and its unique index are created empty, so
`CONCURRENTLY` is not needed and nothing is scanned.

MIGRATION-CLASS (D45 / notice 47b): merged only on Alex's word, and no default
fires on silence.

Reversible. The D51 undo line drops exactly what this adds, including every
publication recorded since. Unset the flag FIRST: with the flag on and the table
gone, each recording attempt logs an ERROR inside its savepoint, and the price
write still commits.

    alembic downgrade ce9935000002

Revision ID: prob_publications
Revises: ce9935000002
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "prob_publications"
down_revision = "ce9935000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "probability_publications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("rev", sa.BigInteger(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.Column("sources", JSONB(), nullable=False),
        sa.Column("event_status", sa.String(20), nullable=True),
        sa.Column("blend_inputs", JSONB(), nullable=False),
        sa.Column("blend_probability", sa.Float(), nullable=True),
        sa.Column("blend_tier", sa.String(16), nullable=True),
        sa.Column("blend_method", sa.String(80), nullable=False),
        sa.Column("source_clocks", JSONB(), nullable=False),
        sa.Column("removed_sources", JSONB(), nullable=False),
        sa.Column("observations", JSONB(), nullable=False),
        sa.Column("coverage", sa.String(32), nullable=False),
        sa.Column("uncovered_keys", JSONB(), nullable=False),
        sa.Column("stream_frame_eligible", sa.Boolean(), nullable=False),
        sa.Column("txn_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "event_id", "rev", name="uq_probability_publications_event_rev"
        ),
    )


def downgrade() -> None:
    op.drop_table("probability_publications")
