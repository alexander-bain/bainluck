"""Add team_identity_mapping table and StatPal columns.

Revision ID: add_team_identity
Revises: nullable_lma_event_id
Create Date: 2026-02-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_team_identity"
down_revision: Union[str, None] = "nullable_lma_event_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- 1. Create team_identity_mapping table --
    op.create_table(
        "team_identity_mapping",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=True),
        sa.Column("source_name", sa.String(300), nullable=True),
        sa.Column("source_abbreviation", sa.String(20), nullable=True),
        sa.Column("sport_key", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes
    op.create_index("ix_team_identity_team_id", "team_identity_mapping", ["team_id"])
    op.create_index("ix_team_identity_source", "team_identity_mapping", ["source"])
    op.create_index("ix_team_identity_source_name", "team_identity_mapping", ["source_name"])
    op.create_index("ix_team_identity_sport_key", "team_identity_mapping", ["sport_key"])

    # Partial unique indexes (WHERE ... IS NOT NULL)
    op.execute(
        "CREATE UNIQUE INDEX uq_tim_source_id ON team_identity_mapping "
        "(source, source_id, sport_key) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tim_source_name ON team_identity_mapping "
        "(source, source_name, sport_key) WHERE source_name IS NOT NULL"
    )

    # -- 2. Add columns to events --
    op.add_column("events", sa.Column("statpal_fixture_id", sa.String(100), nullable=True))
    op.add_column("events", sa.Column("statpal_end_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("commence_time_source", sa.String(20), nullable=True))
    op.create_index("ix_events_statpal_fixture_id", "events", ["statpal_fixture_id"])

    # -- 3. Add column to teams --
    op.add_column("teams", sa.Column("statpal_team_id", sa.String(100), nullable=True))
    op.create_index("ix_teams_statpal_team_id", "teams", ["statpal_team_id"])

    # -- 4. Data migration: copy existing JSONB data to proper columns --
    op.execute(
        "UPDATE events "
        "SET statpal_fixture_id = win_probability_sources->>'statpal_fixture_id' "
        "WHERE win_probability_sources ? 'statpal_fixture_id'"
    )
    op.execute(
        "UPDATE events "
        "SET statpal_end_time = (win_probability_sources->>'statpal_end_time')::timestamptz "
        "WHERE win_probability_sources ? 'statpal_end_time'"
    )


def downgrade() -> None:
    # Drop team_identity_mapping table (includes all indexes)
    op.drop_table("team_identity_mapping")

    # Drop new event columns
    op.drop_index("ix_events_statpal_fixture_id", table_name="events")
    op.drop_column("events", "statpal_fixture_id")
    op.drop_column("events", "statpal_end_time")
    op.drop_column("events", "commence_time_source")

    # Drop new team column
    op.drop_index("ix_teams_statpal_team_id", table_name="teams")
    op.drop_column("teams", "statpal_team_id")
