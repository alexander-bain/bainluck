"""#13229 / 314-B: create retired_team_redirects table for folded duplicate clubs.

MIGRATION-CLASS: merged and run only on Alex's separate release go (314: B).

Creates ``retired_team_redirects``, an empty new table that maps a folded team's
retired ``teams.id``, ``slug``, and ``(sport_id, name)`` to its surviving
``canonical_team_id``. Because the table is brand new and empty, all indexes
build instantaneously during Heroku release with zero locks on existing tables.

Revision ID: retired_team_redirects_13229
Revises: push_devices_177a
"""

import sqlalchemy as sa
from alembic import op

revision = "retired_team_redirects_13229"
down_revision = "push_devices_177a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retired_team_redirects",
        sa.Column(
            "retired_team_id",
            sa.Integer(),
            primary_key=True,
            autoincrement=False,
        ),
        sa.Column("retired_slug", sa.String(200), nullable=True),
        sa.Column("retired_name", sa.String(200), nullable=True),
        sa.Column(
            "sport_id",
            sa.Integer(),
            sa.ForeignKey("sports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "canonical_team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.CheckConstraint(
            "retired_team_id <> canonical_team_id",
            name="ck_retired_team_redirects_not_self",
        ),
    )
    op.create_index(
        "ix_retired_team_redirects_retired_slug",
        "retired_team_redirects",
        ["retired_slug"],
        unique=True,
    )
    op.create_index(
        "ix_retired_team_redirects_sport_id",
        "retired_team_redirects",
        ["sport_id"],
    )
    op.create_index(
        "ix_retired_team_redirects_canonical_team_id",
        "retired_team_redirects",
        ["canonical_team_id"],
    )
    op.create_index(
        "ix_retired_team_redirects_sport_name",
        "retired_team_redirects",
        ["sport_id", "retired_name"],
    )


def downgrade():
    op.drop_index(
        "ix_retired_team_redirects_sport_name",
        table_name="retired_team_redirects",
    )
    op.drop_index(
        "ix_retired_team_redirects_canonical_team_id",
        table_name="retired_team_redirects",
    )
    op.drop_index(
        "ix_retired_team_redirects_sport_id",
        table_name="retired_team_redirects",
    )
    op.drop_index(
        "ix_retired_team_redirects_retired_slug",
        table_name="retired_team_redirects",
    )
    op.drop_table("retired_team_redirects")
