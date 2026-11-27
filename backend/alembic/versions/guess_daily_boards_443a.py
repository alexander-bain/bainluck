"""#12619 / 443-A: create guess_daily_editions and guess_group_entries tables.

MIGRATION-CLASS: waits for Alex's explicit "go" in his window; not executed
before merge authorization.

Stores ONLY the frozen daily /guess card pack per PT calendar day and per-group
finished entries (day_pt, group_code, nickname, nickname_lower, 15 answers,
step_times). Zero account, device, IP, address, or client-score columns.
Both tables are swept after 30 days.

Revision ID: guess_daily_boards_443a
Revises: fm_open_indexes_12818
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "guess_daily_boards_443a"
down_revision = "fm_open_indexes_12818"
branch_labels = None
depends_on = None

_JSON_TYPE = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def upgrade():
    op.create_table(
        "guess_daily_editions",
        sa.Column("day_pt", sa.Date(), nullable=False),
        sa.Column("edition_code", sa.String(length=6), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pack_json", _JSON_TYPE, nullable=False),
        sa.Column("source_snapshot", _JSON_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("day_pt"),
        sa.UniqueConstraint("edition_code", name="uq_guess_daily_editions_code"),
    )
    op.create_table(
        "guess_group_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("day_pt", sa.Date(), nullable=False),
        sa.Column("group_code", sa.String(length=24), nullable=False),
        sa.Column("nickname", sa.String(length=12), nullable=False),
        sa.Column("nickname_lower", sa.String(length=12), nullable=False),
        sa.Column("answers", _JSON_TYPE, nullable=False),
        sa.Column("step_times", _JSON_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "day_pt",
            "group_code",
            "nickname_lower",
            name="uq_guess_group_entries_day_group_nick",
        ),
    )
    op.create_index(
        "ix_guess_group_entries_day_group",
        "guess_group_entries",
        ["day_pt", "group_code"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_guess_group_entries_day_group", table_name="guess_group_entries")
    op.drop_table("guess_group_entries")
    op.drop_table("guess_daily_editions")
