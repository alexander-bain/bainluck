"""Add composite index on events(status, commence_time) for feed queries

Revision ID: add_events_status_idx
Revises: add_line_movement_tbl
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_events_status_idx"
down_revision: Union[str, None] = "add_line_movement_tbl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_events_status_commence",
        "events",
        ["status", "commence_time"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_events_status_commence", table_name="events", if_exists=True)
