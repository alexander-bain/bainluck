"""Add provenance to discover_interactions (pre-training gate).

Enum AS APPLIED BY THIS REVISION: user, warmer, sentinel, gold_session, admin,
unknown. **Six values.** `play` is added by the NEXT revision,
`add_prov_play_value` — see "Why `play` is not in this file" below, which is the
single most important thing to read here.

user         — real user impression/interaction from web/native Discover feed
warmer       — typeahead_warmer / pre-warm background reads that touch the feed
sentinel     — flow_sentinel / calibration_sentinel / grid_sentinel probes
gold_session — labeling surfaces sampling the 250 gold labels (Alex's taste)
admin        — admin tools / manual curls with ADMIN_TOKEN, not user taste
unknown      — any writer that did not stamp provenance; NEVER maps to user
play         — the kid surface (/play). Its own value, never folded into user.
               NOT created here. Added by `add_prov_play_value`.

## Why `play` is not in this file, even though the defect is that it is missing

`C-ADHOC-PROV-CORE P1` is right that a six-value enum does not "omit a case" — it
makes **production PostgreSQL reject every Play interaction at commit** while the
ORM accepts it happily, because the recording double does not enforce the type.
That defect is real and it is being fixed. It is just not fixable *here*.

**This revision has already run in production.** `alembic_version` reads
`add_disc_int_provenance`; `pg_enum` holds exactly the six values above, in that
order, with `play` absent (both re-verified 2026-08-19). Alembic runs a revision
once. Adding `play` to the tuple below therefore changes what a FRESH database
gets and changes nothing at all about production — the `upgrade()` that would
have created it can never execute again. The enum would stay six-valued forever
while every test and every reader of this file believed it was seven.

That is a worse state than the original bug, because the original bug was
visible. So the seventh value is added by a new revision that *has* not run:

    add_typeahead_index -> add_disc_int_provenance -> add_prov_play_value

Both paths then converge on the same enum, **in the same declaration order**:

* fresh database — this revision creates six, `add_prov_play_value` appends
  `play` as the seventh;
* production — this revision already created six, `add_prov_play_value` appends
  `play` as the seventh.

Had `play` been left in the tuple below *and* the new revision added, both paths
would still end at seven values, which is the letter of the requirement — but a
fresh database would order it `user, play, warmer, …` and production
`user, warmer, …, play`. Enum ordinals are what `ORDER BY provenance` and every
btree range scan on the column mean by "order", so CI and production would be
comparing two different types with the same name. The real-Postgres gate would
be green against a shape production does not have. Six here is what makes the
two databases identical rather than merely equinumerous.

The general rule, which this file's own earlier draft states and then broke: **a
migration is a historical record of what was applied.** It may not change meaning
later because application code moved. Application code moved; a new revision is
how that gets expressed.

Nullable with no backfill on live rows: NULL means "not recorded" (pre-column)
and is treated as unknown at read time. A separate backfill heuristic (dry-run,
attended-apply only) re-estimates historical unknowns from the 89% / 23.6%
fingerprints — never unattended rewrites.

This is the gate between Alex's 250 labels and a model that learns his taste
instead of the warmer's. Without this column every dwell/dismiss in
discover_interactions is an unfalsifiable mixture, and interestingness tuning
grades echo as preference.

Revision ID: add_disc_int_provenance
Revises: add_typeahead_index
Create Date: 2026-08-18
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

#: THE SIX VALUES THIS REVISION ACTUALLY CREATED, named once, in enum-ordinal
#: order. `upgrade` and `downgrade` both read this — spelling the list twice is
#: how the two halves drifted apart in the first place, and a downgrade that
#: names a different type than the one it drops leaves the enum behind.
#:
#: FROZEN. This tuple is a fact about a migration that ran on 2026-08-18, not a
#: declaration of what the enum should contain today. Do not add to it. The
#: runtime allowlist lives in `app/utils/discover_provenance.py`, the seventh
#: value lives in `add_prov_play_value.py`, and `tests/test_discover_provenance.py`
#: binds the CHAIN (this tuple + that value) to the allowlist so the three cannot
#: drift apart silently.
PROVENANCE_VALUES_AS_APPLIED = (
    "user",
    "warmer",
    "sentinel",
    "gold_session",
    "admin",
    "unknown",
)


def upgrade() -> None:
    provenance_enum = sa.Enum(
        *PROVENANCE_VALUES_AS_APPLIED, name="discover_provenance"
    )
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
                "produced this row; NULL means pre-column (treat as unknown). "
                "`play` is added by revision add_prov_play_value."
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
    # Dropping the TYPE removes every value it holds, including the `play` that
    # `add_prov_play_value` appended. That is why that revision's own downgrade
    # is a documented no-op: PostgreSQL cannot remove a single enum label, so the
    # only honest place to undo `play` is here, where the whole type goes.
    provenance_enum = sa.Enum(
        *PROVENANCE_VALUES_AS_APPLIED, name="discover_provenance"
    )
    provenance_enum.drop(op.get_bind(), checkfirst=True)
