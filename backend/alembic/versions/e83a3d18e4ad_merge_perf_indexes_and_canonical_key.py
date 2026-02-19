"""merge perf indexes and canonical key

Revision ID: e83a3d18e4ad
Revises: add_perf_indexes, add_canonical_mkt_key
Create Date: 2026-02-19 06:36:10.359447

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e83a3d18e4ad'
down_revision: Union[str, None] = ('add_perf_indexes', 'add_canonical_mkt_key')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
