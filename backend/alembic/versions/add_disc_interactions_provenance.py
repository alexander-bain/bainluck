"""Add provenance to discover_interactions (pre-training gate).

Enum: user, play, warmer, sentinel, gold_session, admin, unknown.

user         — real user impression/interaction from web/native Discover feed
play         — the kid surface (/play). Its own value, never folded into user
warmer       — typeahead_warmer / pre-warm background reads that touch the feed
sentinel     — flow_sentinel / calibration_sentinel / grid_sentinel probes
gold_session — labeling surfaces sampling the 250 gold labels (Alex's taste)
admin        — admin tools / manual curls with ADMIN_TOKEN, not user taste
unknown      — any writer that did not stamp provenance; NEVER maps to user

`play` IS PART OF THIS ENUM AND NOT AN AFTERTHOUGHT (C-ADHOC-PROV-CORE P1).
The receiver already accepts `play` and the Play transport already stamps it, so
a six-value enum does not "omit a case" — it makes **production PostgreSQL
reject every Play interaction at commit**. The reason that was not caught
earlier is worth keeping: the route specimen stored `play` successfully because
the recording double does not enforce the enum. The ORM accepted what the
database would not. A writer/schema split is only visible against a real enum,
which is why this migration's gate now runs against one (see
`tests/test_provenance_enum_real_postgres.py`).

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
# SLOT ASSIGNED by INT-086 at integration, as this file's own header requested.
# Authored against `add_disc_int_market_type`, which was the head when the branch
# was cut but is no longer: LAT-P067's `add_typeahead_index` landed on master at
# `9e0f0f37` about an hour earlier. Left as authored this is TWO HEADS, and two
# heads fail the Heroku release phase — the site does not deploy at all.
#
# Retargeted rather than resolved with a merge revision because the two are
# independent and a linear chain is cheaper to reason about forever: this adds a
# column to `discover_interactions`, `add_typeahead_index` creates a new table.
# Neither touches the other's object, so ordering between them is free.
down_revision = "add_typeahead_index"
branch_labels = None
depends_on = None

#: THE seven values, named once. `upgrade` and `downgrade` both read this, and
#: `app/utils/discover_provenance.py` asserts the receiver's allowlist matches it
#: — because the failure this migration exists to fix was precisely a receiver
#: that accepted a value the enum could not store.
PROVENANCE_VALUES = (
    "user",
    "play",
    "warmer",
    "sentinel",
    "gold_session",
    "admin",
    "unknown",
)


def upgrade() -> None:
    # NOTE: This migration's slot is REQUESTED in .claude/handoff/READY-codex-adhoc-provenance.md.
    # The integrator assigns the final ordering on master (concurrent migration
    # heads merge via a merge revision). Do not renumber locally.
    provenance_enum = sa.Enum(*PROVENANCE_VALUES, name="discover_provenance")
    provenance_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "discover_interactions",
        sa.Column(
            "provenance",
            provenance_enum,
            nullable=True,
            server_default="unknown",
            comment=(
                "user|play|warmer|sentinel|gold_session|admin|unknown — who/what "
                "produced this row; NULL means pre-column (treat as unknown)"
            ),
        ),
    )
    op.create_index(
        "ix_discover_interactions_provenance",
        "discover_interactions",
        ["provenance"],
    )
    # NO DATA UPDATE HERE, deliberately (C-ADHOC-PROV-CORE P1; R3 had already
    # removed it and the extraction put it back).
    #
    # The removed statement was:
    #     UPDATE discover_interactions SET provenance = 'unknown' WHERE ... IS NULL
    #
    # Three reasons it does not belong in a release migration:
    #  1. It is a whole-table write on a large table, inside Heroku's ~5-minute
    #     release phase. A release that times out is a site that does not deploy
    #     (gotcha #31's shape, with an UPDATE instead of an index).
    #  2. It is unnecessary. `server_default='unknown'` covers every NEW row, and
    #     the read path already treats NULL as unknown. The rewrite buys nothing
    #     a reader can observe.
    #  3. It destroys a distinction. NULL means "predates the column"; 'unknown'
    #     means "a writer did not stamp it". Collapsing the first into the second
    #     throws away the only evidence that separates a pre-column row from a
    #     live unstamped one — which is exactly what the attended backfill
    #     heuristic needs in order to re-estimate history.
    #
    # Existing rows stay NULL until that attended dry-run re-estimates them. It
    # never runs unattended.


def downgrade() -> None:
    op.drop_index("ix_discover_interactions_provenance", table_name="discover_interactions")
    op.drop_column("discover_interactions", "provenance")
    # Same seven values as `upgrade`, from the same constant. Spelling the list
    # twice is how the two halves drifted apart in the first place: a downgrade
    # that names a different type than the one it drops leaves the enum behind.
    provenance_enum = sa.Enum(*PROVENANCE_VALUES, name="discover_provenance")
    provenance_enum.drop(op.get_bind(), checkfirst=True)
