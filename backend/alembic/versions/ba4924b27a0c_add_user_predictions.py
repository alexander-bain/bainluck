"""add_user_predictions

Revision ID: ba4924b27a0c
Revises: 9ae5fd410036
Create Date: 2026-04-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'ba4924b27a0c'
down_revision: Union[str, None] = '9ae5fd410036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_predictions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('market_id', sa.Integer(), nullable=False),
        sa.Column('guess', sa.String(10), nullable=False),
        sa.Column('threshold', sa.Integer(), nullable=False),
        sa.Column('actual_probability', sa.Float(), nullable=False),
        sa.Column('correct', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_user_predictions_session_id', 'user_predictions', ['session_id'])


def downgrade() -> None:
    op.drop_table('user_predictions')
