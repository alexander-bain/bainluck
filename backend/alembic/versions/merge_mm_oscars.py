"""Merge add_mm_fields and add_oscars_pool heads.

Revision ID: merge_mm_oscars
Revises: add_mm_fields, add_oscars_pool
Create Date: 2026-03-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "merge_mm_oscars"
down_revision: Union[str, None] = ("add_mm_fields", "add_oscars_pool")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
