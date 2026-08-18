"""Add provenance to discover_interactions (pre-training gate).

Enum: user, warmer, sentinel, gold_session, admin, unknown.

user         — real user impression/interaction from web/native Discover feed
warmer       — typeahead_warmer / pre-warm background reads that touch the feed
sentinel     — flow_sentinel / calibration_sentinel / grid_sentinel probes
gold_session — labeling surfaces sampling the 250 gold labels (Alex's taste)
admin        — admin tools / manual curls with ADMIN_TOKEN, not user taste
unknown      — any writer that did not stamp provenance; NEVER maps to user

Nullable with no backfill on live rows: NULL means "not recorded" (pre-column)
and is treated as unknown at read time. A separate backfill heuristic (dry-run,
attended-apply only) re-estimates historical unknowns from the 89% / 23.6%
fingerprints — never unattended rewrites.

This is the gate between Alex's 250 labels and a model that learns his taste
instead of the warmer's. Without this column every dwell/dismiss in
discover_interactions is unfalsifiably amixture, and interestingness tuning
grades echo as preference.

Revision ID: add_disc_int_provenance
Revises: add_disc_int_market_type
Create Date: 2026-08-18
Slot: REQUESTED — integrator assigns final down_revision / merge head.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "add_disc_int_provenance"
down_revision = "add_disc_int_market_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTE: This migration's slot is REQUESTED in .claude/handoff/READY-codex-adhoc-provenance.md.
    # The integrator assigns the final ordering on master (concurrent migration
    # heads merge via a merge revision). Do not renumber locally.
    provenance_enum = sa.Enum(
        "user", "warmer", "sentinel", "gold_session", "admin", "unknown",
        name="discover_provenance",
    )
    provenance_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "discover_interactions",
        sa.Column(
            "provenance",
            provenance_enum,
            nullable=True,
            server_default="unknown",
            comment="user|warmer|sentinel|gold_session|admin|unknown — who/what produced this row; NULL means pre-column (treat as unknown)",
        ),
    )
    op.create_index(
        "ix_discover_interactions_provenance",
        "discover_interactions",
        ["provenance"],
    )
    # Backfill boundedness — existing rows predating the column are pre-provenance.
    # They stay NULL/unknown until the attended dry-run heuristic re-estimates them
    # per the 89%/23.6% fingerprints; the heuristic never runs unattended.
    op.execute("UPDATE discover_interactions SET provenance = 'unknown' WHERE provenance IS NULL")


def downgrade() -> None:
    op.drop_index("ix_discover_interactions_provenance", table_name="discover_interactions")
    op.drop_column("discover_interactions", "provenance")
    provenance_enum = sa.Enum(
        "user", "warmer", "sentinel", "gold_session", "admin", "unknown",
        name="discover_provenance",
    )
    provenance_enum.drop(op.get_bind(), checkfirst=True)
