"""add_image_and_hook

Revision ID: 9ae5fd410036
Revises: c84a1374d792
Create Date: 2026-04-29 21:13:15.160394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ae5fd410036'
down_revision: Union[str, None] = 'c84a1374d792'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('futures_markets', sa.Column('image_url', sa.String(500), nullable=True))
    op.add_column('futures_markets', sa.Column('hook_description', sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column('futures_markets', 'hook_description')
    op.drop_column('futures_markets', 'image_url')
