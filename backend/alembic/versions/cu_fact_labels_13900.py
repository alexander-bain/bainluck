"""#13900: create cu_fact_labels table for dual-rater Content Understanding fact labeling.

MIGRATION-CLASS: waits for Alex's own merge line naming the exact head after
Fable's ACCEPT and after migrations in line (#13691 metrickit_payloads_12309,
then #13865 poll_open_outcomes_13673) land on master and this migration's
``down_revision`` is moved onto ``poll_open_outcomes_13673``.

Until `#13865` lands on master, ``down_revision`` temporarily follows
``metrickit_payloads_12309`` (current master head from ``#13691``) so Alembic
single-head checks and hosted CI/Vercel preview stay green; once ``#13865`` lands,
this moves once more onto ``poll_open_outcomes_13673``.

Revision ID: cu_fact_labels_13900
Revises: metrickit_payloads_12309
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "cu_fact_labels_13900"
down_revision = "metrickit_payloads_12309"
branch_labels = None
depends_on = None

_JSON_TYPE = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def upgrade():
    op.create_table(
        "cu_fact_labels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_split", sa.String(length=16), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("rater", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("subjects_answer", _JSON_TYPE, nullable=True),
        sa.Column("event_date_answer", sa.String(length=32), nullable=True),
        sa.Column("no_single_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("geography_answer", sa.String(length=64), nullable=True),
        sa.Column("structure_answer", sa.String(length=32), nullable=True),
        sa.Column("claim_frame", _JSON_TYPE, nullable=True),
        sa.Column("stakes", sa.SmallInteger(), nullable=True),
        sa.Column("breadth", sa.SmallInteger(), nullable=True),
        sa.Column("evidence_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["market_id"], ["futures_markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_split",
            "market_id",
            "rater",
            "role",
            name="uq_cu_fact_labels_split_market_rater_role",
        ),
    )
    op.create_index(
        "ix_cu_fact_labels_split_market",
        "cu_fact_labels",
        ["dataset_split", "market_id"],
        unique=False,
    )
    op.create_index(
        "ix_cu_fact_labels_split_rater_role",
        "cu_fact_labels",
        ["dataset_split", "rater", "role"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_cu_fact_labels_split_rater_role", table_name="cu_fact_labels")
    op.drop_index("ix_cu_fact_labels_split_market", table_name="cu_fact_labels")
    op.drop_table("cu_fact_labels")
