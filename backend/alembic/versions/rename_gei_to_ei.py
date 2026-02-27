"""Rename GEI (Game Excitement Index) to EI (Excitement Index).

Renames columns on events table and the gei_percentiles table to use
the standard "EI" naming from sports analytics literature.

Revision ID: rename_gei_to_ei
Revises: add_team_stats_cols
"""

from alembic import op


# revision identifiers
revision = "rename_gei_to_ei"
down_revision = "add_team_stats_cols"
branch_labels = None
depends_on = None


def upgrade():
    # Rename columns on events table
    op.alter_column("events", "raw_gei", new_column_name="raw_ei")
    op.alter_column("events", "gei_components", new_column_name="ei_metadata")
    op.alter_column("events", "gei_computed_at", new_column_name="ei_computed_at")

    # Rename the percentiles table
    op.rename_table("gei_percentiles", "ei_percentiles")

    # Rename column in the percentiles table
    op.alter_column("ei_percentiles", "raw_gei_threshold", new_column_name="raw_ei_threshold")


def downgrade():
    # Reverse column renames on events
    op.alter_column("events", "raw_ei", new_column_name="raw_gei")
    op.alter_column("events", "ei_metadata", new_column_name="gei_components")
    op.alter_column("events", "ei_computed_at", new_column_name="gei_computed_at")

    # Reverse table rename
    op.rename_table("ei_percentiles", "gei_percentiles")

    # Reverse column rename in percentiles table
    op.alter_column("gei_percentiles", "raw_ei_threshold", new_column_name="raw_gei_threshold")
