"""merge_heads

Revision ID: c84a1374d792
Revises: add_completed_at, add_volume_to_fm, multi_pick_per_match
Create Date: 2026-04-29 21:13:07.625506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c84a1374d792'
down_revision: Union[str, None] = ('add_completed_at', 'add_volume_to_fm', 'multi_pick_per_match')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
