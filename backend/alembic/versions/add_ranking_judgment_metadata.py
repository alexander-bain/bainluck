"""add label_metadata to ranking_judgments

Revision ID: b6c7d8e9f0a1
Revises: e2f3a4b5c6d7
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("ranking_judgments", sa.Column("label_metadata", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("ranking_judgments", "label_metadata")
