"""Event graph Phase 1: containers, anchors, edges, participants. ADDITIVE ONLY.

#2927. Spec: ``.claude/handoff/ARTIFACT-LANE1B-CONTAINERS-SPEC.md`` §1-§3, §5 M1.
Authorised by Alex's verbatim "go 2927", Sat 2026-09-05 7:31pm PT, recorded in
``.claude/handoff/ALEX-GO-2927.md``. That go authorises **this migration only**;
the backfills in spec §5 M2-M4 are separate and run under D51.

WHAT THIS DOES, EXHAUSTIVELY. Creates four new tables and adds one nullable
column to ``market_match_receipts``. **Nothing is altered. Nothing is dropped.
No existing column changes type, nullability or default. No data is written or
moved.** Nothing in the application reads any of it — the assembly job that
will is a separate, read-only, D51-reversible ship.

THE UNDO LINE, which ships with it (D51):

    alembic downgrade uq_event_espn_id

and what that runs is exactly: drop ``market_match_receipts.container_id``,
then ``DROP TABLE event_participants, event_edges, container_provider_anchors,
containers``. Because the tables are new and empty, the downgrade destroys no
pre-existing data — the only rows it can lose are rows this program wrote.

DEPLOY SAFETY (gotcha #31, the May 22 outage). Four ``CREATE TABLE``s on empty
relations, twelve indexes over zero rows, and one ``ADD COLUMN`` of a NULLABLE
column with **no default** — which in Postgres 11+ is a catalogue-only rewrite
even on ``market_match_receipts``'s ~450k rows. The Heroku release phase's
~5-minute timeout is not in play and no ``CONCURRENTLY`` is needed or
permitted here. The one real cost is the ``ADD COLUMN``'s ACCESS EXCLUSIVE lock
on ``market_match_receipts``, held for the catalogue update only; the matcher
upserts into that table every 15 minutes and will block for milliseconds, not
wait behind a rewrite.

TABLE CREATION ORDER IS LOAD-BEARING. ``event_edges.receipt_id`` references
``market_match_receipts`` and ``market_match_receipts.container_id`` references
``containers``, so the two tables reference each other. This is not a cycle
only because the column is added last: containers -> anchors -> edges ->
participants -> ALTER receipts. Reordering will fail at release time, on
production, in the release phase — which is the worst place to find it.

COLUMN NAMES ``class`` AND ``position`` WERE CHECKED, NOT ASSUMED. Measured
against production's ``pg_get_keywords()`` before this was written: ``class``
is ``unreserved`` and ``position`` is ``unreserved (cannot be function or type
name)``. Both are safe as unquoted column names in raw SQL. ``order`` — which
``position`` replaces — is not, which is why the spec avoided it.

Revision ID: containers_phase1
Revises: uq_event_espn_id
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic. `containers_phase1` is 17 characters,
# inside the 32-character limit (gotcha #1).
revision = "containers_phase1"
down_revision = "uq_event_espn_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 1. containers --------------------------------------------------
    op.create_table(
        "containers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("sport_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="scheduled",
            nullable=False,
        ),
        sa.Column("parent_container_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sport_id"], ["sports.id"]),
        # SET NULL, not CASCADE: deleting "US Open 2026" must orphan its draws,
        # not silently delete five containers and everything edged to them.
        sa.ForeignKeyConstraint(
            ["parent_container_id"], ["containers.id"], ondelete="SET NULL"
        ),
        # A one-hop cycle is expressible as a CHECK and therefore refused here.
        # Longer cycles cannot be, and belong to the assembly job's walk.
        sa.CheckConstraint(
            "parent_container_id IS NULL OR parent_container_id <> id",
            name="ck_container_not_own_parent",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # The public identity: the slug IS the URL, so two containers cannot claim
    # one hub. Index names match `Container.__table_args__` exactly.
    op.create_index("uq_container_slug", "containers", ["slug"], unique=True)
    op.create_index("ix_container_kind_status", "containers", ["kind", "status"])
    op.create_index("ix_container_parent", "containers", ["parent_container_id"])
    op.create_index(
        "ix_container_sport_window", "containers", ["sport_id", "window_start"]
    )

    # -- 2. container_provider_anchors ----------------------------------
    op.create_table(
        "container_provider_anchors",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("container_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("sport", sa.String(length=32), nullable=True),
        sa.Column("provider_id", sa.String(length=200), nullable=False),
        sa.Column("id_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "claim_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["container_id"], ["containers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # THE constraint this table exists for: one provider id names ONE
    # container, within its own namespace. A second claim raises — it never
    # silently no-ops (D55).
    #
    # ``sport`` IS IN THE KEY, and ``NULLS NOT DISTINCT`` is what makes it hold
    # (CERT-2001). Without ``sport`` the key contradicts D55's explicit
    # ``(provider, sport, id)`` namespace: ESPN tournament ``1234`` in tennis
    # and ``1234`` in golf are different tournaments and the second would be
    # REFUSED, so a whole hub goes missing rather than wrong. And with ``sport``
    # but WITHOUT ``NULLS NOT DISTINCT`` the constraint quietly evaporates for
    # every provider that does not namespace by sport, because Postgres treats
    # each NULL as distinct and would accept both rows. PG 15+ feature; CI runs
    # postgres:15 and production runs 17.10.
    op.create_index(
        "uq_container_anchor",
        "container_provider_anchors",
        ["provider", "sport", "id_kind", "provider_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "ix_container_anchor_container",
        "container_provider_anchors",
        ["container_id"],
    )

    # -- 3. event_edges --------------------------------------------------
    op.create_table(
        "event_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=False),
        sa.Column("parent_type", sa.String(length=16), nullable=False),
        sa.Column("child_id", sa.BigInteger(), nullable=False),
        sa.Column("child_type", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("class", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("receipt_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # No FK on parent_id/child_id — the type varies. The integrity is
        # bought back by the nightly invariant check (spec §2), which is part
        # of this ship and not a follow-up.
        sa.ForeignKeyConstraint(
            ["receipt_id"], ["market_match_receipts.id"], ondelete="SET NULL"
        ),
        # A `contains` member with no class is a member the hub cannot put in a
        # section. The answer for "could not classify" is 'unclassified', never
        # NULL — an unclassified member must stay visible.
        sa.CheckConstraint(
            "kind <> 'contains' OR class IS NOT NULL",
            name="ck_event_edge_contains_has_class",
        ),
        sa.CheckConstraint(
            "NOT (parent_type = child_type AND parent_id = child_id)",
            name="ck_event_edge_not_self",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_event_edge_confidence_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # The ON CONFLICT target assembly upserts against — what makes a re-run
    # idempotent instead of duplicating every member.
    op.create_index(
        "uq_event_edge",
        "event_edges",
        ["parent_type", "parent_id", "child_type", "child_id", "kind"],
        unique=True,
    )
    op.create_index(
        "ix_event_edge_child", "event_edges", ["child_type", "child_id", "kind"]
    )
    # The hub's own read: this container's members, by section.
    op.create_index(
        "ix_event_edge_parent",
        "event_edges",
        ["parent_type", "parent_id", "kind", "class"],
    )

    # -- 4. event_participants -------------------------------------------
    op.create_table(
        "event_participants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=True),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.CheckConstraint("position >= 0", name="ck_event_participant_position"),
        sa.PrimaryKeyConstraint("id"),
    )
    # One participant per slot: what stops a re-run turning a doubles pair
    # into four.
    op.create_index(
        "uq_event_participant_slot",
        "event_participants",
        ["event_id", "side", "position"],
        unique=True,
    )
    op.create_index(
        "ix_event_participant_entity",
        "event_participants",
        ["entity_type", "entity_id"],
    )
    op.create_index("ix_event_participant_event", "event_participants", ["event_id"])

    # -- 5. the receipt learns about containers ---------------------------
    # LAST, because it closes the reference loop (see the module docstring).
    # Nullable with no default: catalogue-only on Postgres 11+, so the ACCESS
    # EXCLUSIVE lock is held for the metadata update and not for a rewrite of
    # ~450k rows.
    op.add_column(
        "market_match_receipts",
        sa.Column("container_id", sa.BigInteger(), nullable=True),
    )
    # SET NULL, not CASCADE: deleting a container must not delete the evidence
    # of what it refused. A container rebuilt after a bad assembly is exactly
    # when those receipts are worth most.
    op.create_foreign_key(
        "fk_match_receipt_container",
        "market_match_receipts",
        "containers",
        ["container_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_match_receipt_container", "market_match_receipts", ["container_id"]
    )


def downgrade() -> None:
    """Exactly the undo the go authorised: drop the column, drop the tables.

    Reverse order of ``upgrade``. Indexes and constraints go with their tables;
    only the ``market_match_receipts`` additions need dropping by hand, because
    that table survives.
    """
    op.drop_index("ix_match_receipt_container", table_name="market_match_receipts")
    op.drop_constraint(
        "fk_match_receipt_container", "market_match_receipts", type_="foreignkey"
    )
    op.drop_column("market_match_receipts", "container_id")

    op.drop_table("event_participants")
    op.drop_table("event_edges")
    op.drop_table("container_provider_anchors")
    op.drop_table("containers")
