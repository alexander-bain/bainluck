"""Add auth and personalization tables: user_preferences, user_pins, extend user_favorites and teams.

Revision ID: add_auth_personalization
Revises: add_winprob_dedup_cols
Create Date: 2026-02-10
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'add_auth_personalization'
down_revision: Union[str, None] = 'add_winprob_dedup_cols'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # --- teams: add location column ---
    op.add_column('teams',
        sa.Column('location', sa.String(100), nullable=True))

    # --- users: add photo_url column ---
    op.add_column('users',
        sa.Column('photo_url', sa.String(512), nullable=True))

    # --- user_favorites: add relationship, source, weight columns ---
    op.add_column('user_favorites',
        sa.Column('relationship', sa.String(20), nullable=False, server_default='follow'))
    op.add_column('user_favorites',
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'))
    op.add_column('user_favorites',
        sa.Column('weight', sa.Numeric(3, 2), nullable=False, server_default='1.00'))

    # --- user_preferences: new table ---
    op.create_table('user_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  unique=True, nullable=False),
        sa.Column('home_location', sa.String(100), nullable=True),
        sa.Column('sport_affinities', JSONB(), nullable=True, server_default='{}'),
        sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('onboarding_raw', JSONB(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- user_pins: new table ---
    op.create_table('user_pins',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('pin_type', sa.String(20), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'pin_type', 'target_id', name='uq_user_pin'),
    )
    op.create_index('ix_user_pins_user_id', 'user_pins', ['user_id'])


def downgrade() -> None:
    op.drop_table('user_pins')
    op.drop_table('user_preferences')

    op.drop_column('user_favorites', 'weight')
    op.drop_column('user_favorites', 'source')
    op.drop_column('user_favorites', 'relationship')

    op.drop_column('users', 'photo_url')
    op.drop_column('teams', 'location')
