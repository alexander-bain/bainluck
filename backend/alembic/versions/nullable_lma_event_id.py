"""Make line_movement_analyses.event_id nullable for audit results.

Audit findings (canonical key, prediction market, related futures)
may not be tied to a specific event.

Revision ID: nullable_lma_event_id
Revises: add_events_status_idx
Create Date: 2026-02-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "nullable_lma_event_id"
down_revision: Union[str, None] = "add_events_status_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "line_movement_analyses",
        "event_id",
        nullable=True,
        existing_type=sa.Integer(),
    )


def downgrade() -> None:
    # Delete rows with NULL event_id before re-adding NOT NULL constraint
    op.execute(
        "DELETE FROM line_movement_analyses WHERE event_id IS NULL"
    )
    op.alter_column(
        "line_movement_analyses",
        "event_id",
        nullable=False,
        existing_type=sa.Integer(),
    )
