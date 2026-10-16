"""#683: a separate store for Kalshi historical-tier (archive) price intervals.

THE SHIP. A settled Kalshi question that has no price history gets back its
real pre-resolution probability journey on the web and native charts, with
archive provenance on every point and honest forecast eligibility.

WHY A SEPARATE STORE (Goal Root, ``ROOT-STORAGE-DECISION.md``, 2026-10-15).
``futures_odds_snapshots`` has no unique key and no provenance beyond
``bookmaker``, and every calibration phase reads it without a bookmaker filter.
An archive row written there would enter the published Accuracy curve and flip
every zero-snapshot probe. New tables leave every existing reader unchanged.
A reader that wants archive evidence has to join it explicitly.

WHAT THIS DOES, EXHAUSTIVELY. It creates three new, empty tables, their
constraints and three b-tree indexes. It writes no data, alters no existing
table and adds no column. The indexes are built on empty tables, so gotcha #31
does not apply.

* ``kalshi_archive_imports``: one row per attended apply of one reviewed,
  content-addressed plan. It records the ids that apply inserted, and each
  row's version and content seal as stored. A restore therefore removes only
  that import's own rows, and refuses if any of them changed afterwards.
* ``kalshi_archive_outcome_evidence``: per import and outcome, the identity and
  forecast-cutoff evidence the apply revalidated. It is kept apart from the
  price observations, and exactly one of cutoff or refusal is set.
* ``kalshi_archive_intervals``: the observations. A real UNIQUE (outcome,
  period, interval end) makes a re-import conflict instead of doubling. CHECKs
  refuse an interval at or after the venue's settlement, a probability outside
  (0, 1), a span that is not its period, and a provider echo that names
  another market.

LOCKS. The two foreign keys to ``futures_outcomes`` take SHARE ROW EXCLUSIVE on
it while the constraint is added, so they briefly wait behind and block
writers of that table. ``alembic/env.py`` arms ``lock_timeout`` and retries the
batch (#2724), so a long writer makes this retry rather than queue the price
writers behind it. Nothing scans ``futures_outcomes``: the new tables are empty.

MIGRATION-CLASS (D45 / notice 47b). It merges only when Alex says so, and no
merge-on-silence default exists. Executing it does not enable anything: no
task, route flag or schedule writes these tables. The only writer is the
attended ``scripts/kalshi_archive_import.py apply``.

Reversible while empty. The undo line is

    alembic downgrade fo_trgm_fastupdate_off

After an import, restore that import first (``kalshi_archive_import.py
restore``). The downgrade drops whatever the tables still hold.

Revision ID: kalshi_archive_store_683
Revises: fo_trgm_fastupdate_off
Create Date: 2026-10-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Gotcha #1: revision ids stay <= 32 characters.
revision = "kalshi_archive_store_683"
down_revision = "fo_trgm_fastupdate_off"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kalshi_archive_imports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("import_key", sa.String(64), nullable=False),
        sa.Column("plan_digest", sa.String(64), nullable=False),
        sa.Column("archive_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "inserted_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "outcome_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "report",
            postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "inserted_seals",
            postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "evidence_versions",
            postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.UniqueConstraint("import_key", name="kalshi_archive_imports_import_key_key"),
        sa.CheckConstraint(
            "status IN ('applying', 'applied', 'partial', 'failed', 'restored')",
            name="ck_kai_status",
        ),
        sa.CheckConstraint("char_length(plan_digest) = 64", name="ck_kai_plan_digest"),
        sa.CheckConstraint(
            "(status = 'restored') = (restored_at IS NOT NULL)", name="ck_kai_restored"
        ),
    )
    op.create_index(
        "ix_kalshi_archive_imports_plan_digest",
        "kalshi_archive_imports",
        ["plan_digest"],
    )

    op.create_table(
        "kalshi_archive_outcome_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "import_id",
            sa.BigInteger(),
            sa.ForeignKey("kalshi_archive_imports.id"),
            nullable=False,
        ),
        sa.Column(
            "outcome_id",
            sa.Integer(),
            sa.ForeignKey("futures_outcomes.id"),
            nullable=False,
        ),
        sa.Column("market_ticker", sa.String(120), nullable=False),
        sa.Column("event_ticker", sa.String(120), nullable=False),
        sa.Column("period_minutes", sa.SmallInteger(), nullable=False),
        sa.Column("venue_open_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("venue_settlement_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archive_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage", sa.String(20), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("cutoff_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("forecast_cutoff_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cutoff_refusal", sa.String(80), nullable=True),
        sa.Column("plan_forecast_cutoff_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_cutoff_refusal", sa.String(80), nullable=True),
        sa.Column("windows", postgresql.JSONB(), nullable=False),
        sa.Column(
            "owed_windows",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("import_id", "outcome_id", name="uq_kaoe_import_outcome"),
        sa.CheckConstraint(
            "(forecast_cutoff_ts IS NULL) <> (cutoff_refusal IS NULL)",
            name="ck_kaoe_cutoff_xor_refusal",
        ),
        sa.CheckConstraint(
            "venue_settlement_ts < archive_cutoff", name="ck_kaoe_archive_tier"
        ),
        sa.CheckConstraint(
            "forecast_cutoff_ts IS NULL OR forecast_cutoff_ts <= venue_settlement_ts",
            name="ck_kaoe_cutoff_before_settlement",
        ),
        sa.CheckConstraint("char_length(input_fingerprint) = 64", name="ck_kaoe_fp"),
        sa.CheckConstraint("period_minutes IN (1, 60)", name="ck_kaoe_period"),
    )
    op.create_index(
        "ix_kalshi_archive_outcome_evidence_outcome_id",
        "kalshi_archive_outcome_evidence",
        ["outcome_id"],
    )

    op.create_table(
        "kalshi_archive_intervals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "import_id",
            sa.BigInteger(),
            sa.ForeignKey("kalshi_archive_imports.id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.BigInteger(),
            sa.ForeignKey("kalshi_archive_outcome_evidence.id"),
            nullable=False,
        ),
        sa.Column(
            "outcome_id",
            sa.Integer(),
            sa.ForeignKey("futures_outcomes.id"),
            nullable=False,
        ),
        sa.Column("market_ticker", sa.String(120), nullable=False),
        sa.Column("event_ticker", sa.String(120), nullable=False),
        sa.Column("period_minutes", sa.SmallInteger(), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venue_settlement_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Numeric(7, 6), nullable=False),
        sa.Column("price_basis", sa.String(20), nullable=False),
        sa.Column("volume", sa.String(40), nullable=True),
        sa.Column("echoed_ticker", sa.String(120), nullable=False),
        sa.Column("raw_response_sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admission_at_plan", sa.String(20), nullable=False),
        sa.Column("admission_at_apply", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "outcome_id", "period_minutes", "interval_end", name="uq_kai_interval"
        ),
        sa.CheckConstraint("period_minutes IN (1, 60)", name="ck_kaiv_period"),
        sa.CheckConstraint(
            "date_part('epoch', interval_end - interval_start) = period_minutes * 60",
            name="ck_kaiv_span",
        ),
        sa.CheckConstraint(
            "interval_end < venue_settlement_ts", name="ck_kaiv_before_settlement"
        ),
        sa.CheckConstraint(
            "probability > 0 AND probability < 1", name="ck_kaiv_probability"
        ),
        sa.CheckConstraint(
            "price_basis IN ('traded_interval', 'quote_only')", name="ck_kaiv_basis"
        ),
        sa.CheckConstraint("echoed_ticker = market_ticker", name="ck_kaiv_echo"),
        sa.CheckConstraint("char_length(raw_response_sha256) = 64", name="ck_kaiv_sha"),
        sa.CheckConstraint(
            "admission_at_plan IN ('forecast', 'reader_only')", name="ck_kaiv_plan_adm"
        ),
        sa.CheckConstraint(
            "admission_at_apply IN ('forecast', 'reader_only')",
            name="ck_kaiv_apply_adm",
        ),
    )
    op.create_index(
        "ix_kaiv_outcome_end", "kalshi_archive_intervals", ["outcome_id", "interval_end"]
    )
    op.create_index("ix_kaiv_import", "kalshi_archive_intervals", ["import_id"])


def downgrade() -> None:
    op.drop_table("kalshi_archive_intervals")
    op.drop_table("kalshi_archive_outcome_evidence")
    op.drop_table("kalshi_archive_imports")
