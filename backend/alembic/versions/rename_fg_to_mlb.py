"""Rename fangraphs source key to mlb in win_prob_snapshots.

Revision ID: rename_fg_to_mlb
Revises: rename_fm_metadata
Create Date: 2026-03-05
"""

# revision identifiers
revision = "rename_fg_to_mlb"
down_revision = "rename_fm_metadata"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("UPDATE win_prob_snapshots SET source = 'mlb' WHERE source = 'fangraphs'")


def downgrade():
    op.execute("UPDATE win_prob_snapshots SET source = 'fangraphs' WHERE source = 'mlb'")
