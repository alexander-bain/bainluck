"""Add line_movement_analyses table for cached LLM explanations.

Revision ID: add_line_movement_tbl
Revises: allow_multi_relation
Create Date: 2026-02-21
"""
from typing import Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision: str = 'add_line_movement_tbl'
down_revision: Union[str, None] = 'allow_multi_relation'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        'line_movement_analyses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('events.id'), nullable=False, index=True),
        sa.Column('movement_data', JSONB(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('disagreement_explanation', sa.Text(), nullable=True),
        sa.Column('disagreement_data', JSONB(), nullable=True),
        sa.Column('analysis_type', sa.String(30), nullable=False, server_default='line_movement'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('line_movement_analyses')
