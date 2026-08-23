"""The folded #1946 slot: `event_provider_anchors` + `settlement_captures`.

Both tables are created EMPTY. Nothing is backfilled here, `events` is not
touched, and no index is built `CONCURRENTLY`.

## Why one revision holds two tables

The #1946 migration slot was GRANTED to lane1 for `event_provider_anchors`
(2026-08-21, INT-107, Alex instructing), then AMENDED and RATIFIED by the same
grantor to fold in `settlement_captures`. The grant record is
`.claude/handoff/MIGRATION-SLOT-REQUEST-1946.md`; the fold is recorded on #1946
as comment 5375076478.

The fold exists because `settlement_captures` sits under a hard, one-way
external date. Kalshi's market retention is measured (`app/utils/kalshi_retention.py`)
at >=74 and <86 days, and the `0-7` bucket holds **1,202 markets that become
permanently unverifiable on 2026-08-28**. Retention does not run backwards, so
queueing a second empty `CREATE TABLE` behind this one would have spent that
date to buy nothing.

CLAUDE.md's never-two-migrations rule and gotcha #8 are about two Alembic HEADS
racing. Two `CREATE TABLE`s inside one head is not that shape — it is the safer
one, because there is exactly one `down_revision` and one thing to revert.

## Why `CONCURRENTLY` is absent, deliberately

Gotcha #31 bans `CREATE INDEX CONCURRENTLY` in Alembic because Heroku's release
phase times out (~5 min) building an index on a LARGE table. Both tables here
are created in this same revision and therefore hold **zero rows** when their
indexes are built. Plain `CREATE INDEX` on an empty table is instant, and it is
the correct choice; `CONCURRENTLY` cannot run inside the migration's transaction
anyway. Gotcha #31 does not apply. This was pre-answered and accepted in the
grant.

## Why there is no backfill here

Populating `event_provider_anchors` from the three existing `events` provider-id
columns is bounded, oldest-first background work (#1946 Item 8), and it is
additionally gated on a sink census that has not been taken. Populating
`settlement_captures` is what the sweep runner does (#2077). A backfill inside
the release phase is precisely how gotcha #31 happened.

## Table 1 — `event_provider_anchors` (#1946)

Ruling 048 says an id-less claim never absorbs, and bounds the duplicates that
follow with one clause: *"id-keyed reconciliation drains the duplicate when an
id arrives."* Measured over the whole population on 2026-08-20, that clause is
unexecutable: `AWAITING_ANCHOR` = **0 of 74,181** rows, with 99.61% in
`NO_ANCHOR_CHANNEL` — the creating provider (`kalshi` 73,678 / `polymarket` 503)
has no id column on `events` at all, against exactly three that exist
(`external_id`, `espn_id`, `statpal_fixture_id`). Not a lagging drain, a
structurally impossible one. Alex ruled OPTION A: build the channel.

`id_kind` is the load-bearing column and the reason a table is safe where a
fourth scalar column would not be. **Only `id_kind = 'game'` may anchor an
absorption.** A Kalshi player-prop ticker and a Polymarket `conditionId` are
`market`; a Polymarket event id is `container`. All three are worth recording —
they are how an anchor is discovered — but only one of them asserts "these two
rows are the same game". A table that stored them without saying which kind they
are would rebuild ruling 048's original defect with better indexing. The unique
index therefore includes `id_kind`, so one value may legitimately appear as more
than one kind.

The three existing provider-id columns on `events` **stay**. Too much live code
reads them to move them in the same change, and this revision deliberately does
not propose it.

### ⚠️ This table has NO ORM model yet, and that is on purpose

`app/models/models.py` declares no `EventProviderAnchor`. The consumers
(#1946 Items 6/8/9/10) are HELD behind the Item-8 sink census, and the grant is
clearance to CREATE the table, not to fill or wire it.

The consequence is worth stating loudly, because it will bite whoever runs
autogenerate next: **`alembic revision --autogenerate` will propose
`op.drop_table("event_provider_anchors")`** until that model lands, because
autogenerate diffs the database against `Base.metadata` and this table is in
one and not the other. Do not accept that drop. `settlement_captures` has no
such hazard — its model is on master at `1f03d742`.

## Table 2 — `settlement_captures` (#2077)

Mirrors `app.models.models.SettlementCapture`, merged to master in PR #2093.
Append-only, and write-only with respect to grading: nothing in the capture path
writes `futures_outcomes.is_winner`. It records what a settlement source SAID
and when we asked; a separate reviewable step decides what to do about it.

The CHECK constraint is the invariant of that design enforced by the DATABASE
and not merely by the dataclass — a caller that bypasses the writer still cannot
record a winner it was never told:

    (disposition = 'settled') = (winning_outcome IS NOT NULL)

### 🔎 The grant says "+3 indexes"; the merged ORM declares SIX

Reported rather than quietly reconciled in either direction. The grant's
Condition 3 was written from the design sketch; `SettlementCapture` as merged
also carries `index=True` on `market_id`, `disposition`, `sweep_id` and
`captured_at`, which SQLAlchemy renders as four more single-column indexes on
top of the two composites.

This file creates **all six, matching the ORM exactly**. That is the deliberate
call: a migration that disagrees with its model is a permanent autogenerate
diff and a trap for the next author, and index count is not a second *cause* —
Condition 3 governs causes (two tables), not statement counts. Creating fewer
than the model declares would be the drift.

Two of the six are prefix-redundant and could be dropped later **in the model
first**: `ix_settlement_captures_market_id` is a leading-column duplicate of
`ix_settlement_captures_market_time (market_id, captured_at)`, and
`ix_settlement_captures_sweep_id` of
`ix_settlement_captures_sweep_disp (sweep_id, disposition)`. On an empty table
they cost nothing today, and pruning them here — without touching the model —
would create exactly the divergence described above. Flagged for #2077, not
acted on in a granted slot.

## Downgrade

Two real `DROP TABLE`s, not `pass` (grant Condition 4). Both tables start empty
and nothing reads either of them at the moment this revision lands, so the
revert is genuinely lossless at that point.

Revision ID: anchors_and_captures
Revises: add_prov_play_value
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "anchors_and_captures"
down_revision = "add_prov_play_value"  # re-read from `alembic heads` in the turn this file was written
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------- #1946
    op.create_table(
        "event_provider_anchors",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        # odds_api | espn | statpal | kalshi | polymarket
        sa.Column("source", sa.String(length=32), nullable=False),
        # ticker / conditionId / fixture id
        sa.Column("source_id", sa.String(length=200), nullable=False),
        # 'game' | 'market' | 'container' — only 'game' may anchor an absorption
        sa.Column("id_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # provenance of the claim that attached this anchor
        sa.Column("claim_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Identity: one (source, source_id) per kind. `id_kind` is IN the key so a
    # value may appear as both a 'market' and a 'container' without collision.
    op.create_index(
        "uq_anchor_source_id",
        "event_provider_anchors",
        ["source", "source_id", "id_kind"],
        unique=True,
    )
    op.create_index("ix_anchor_event", "event_provider_anchors", ["event_id"])
    op.create_index("ix_anchor_first_seen", "event_provider_anchors", ["first_seen_at"])

    # ---------------------------------------------------------------- #2077
    op.create_table(
        "settlement_captures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("disposition", sa.String(length=40), nullable=False),
        sa.Column("winning_outcome", sa.Text(), nullable=True),
        sa.Column("answered_by", sa.String(length=40), nullable=True),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("candidate_reason", sa.String(length=40), nullable=False),
        sa.Column("days_remaining_at_capture", sa.Integer(), nullable=True),
        sa.Column("sweep_id", sa.String(length=64), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["market_id"], ["futures_markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # The invariant, enforced by the database and not only the dataclass.
        sa.CheckConstraint(
            "(disposition = 'settled') = (winning_outcome IS NOT NULL)",
            name="ck_settlement_capture_winner_requires_settled",
        ),
    )
    # All six, matching `SettlementCapture.__table__` exactly — see the docstring
    # for why the count differs from the grant's sketch.
    op.create_index("ix_settlement_captures_market_id", "settlement_captures", ["market_id"])
    op.create_index("ix_settlement_captures_disposition", "settlement_captures", ["disposition"])
    op.create_index("ix_settlement_captures_sweep_id", "settlement_captures", ["sweep_id"])
    op.create_index("ix_settlement_captures_captured_at", "settlement_captures", ["captured_at"])
    # The burn-down read: "what have we saved, per bucket, per source".
    op.create_index(
        "ix_settlement_captures_sweep_disp", "settlement_captures", ["sweep_id", "disposition"]
    )
    # The re-probe read: newest capture per market.
    op.create_index(
        "ix_settlement_captures_market_time", "settlement_captures", ["market_id", "captured_at"]
    )


def downgrade() -> None:
    """Two real drops (grant Condition 4), reverse order of creation.

    `DROP TABLE` removes the table's own indexes, constraints and the CHECK with
    it, so they are not dropped individually.
    """
    op.drop_table("settlement_captures")
    op.drop_table("event_provider_anchors")
