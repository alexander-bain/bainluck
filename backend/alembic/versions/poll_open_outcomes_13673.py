"""Add the price poll's admission fields to the open-outcomes copy.

The columns are nullable with no defaults, so the existing rows stay in
place. The scheduled maintainer fills them after release.

Revision ID: poll_open_outcomes_13673
Revises: retired_team_redirects_13229
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "poll_open_outcomes_13673"
down_revision = "retired_team_redirects_13229"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "open_futures_outcomes", sa.Column("external_id", sa.String(200), nullable=True)
    )
    op.add_column(
        "open_futures_outcomes", sa.Column("is_winner", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "open_futures_outcomes", sa.Column("resolution_source", sa.String(30), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("open_futures_outcomes", "resolution_source")
    op.drop_column("open_futures_outcomes", "is_winner")
    op.drop_column("open_futures_outcomes", "external_id")
