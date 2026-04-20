"""Allow multiple picks per match (one per outcome).

Revision ID: multi_pick_per_match
Revises: add_wrestlemania
Create Date: 2026-04-18
"""

revision = "multi_pick_per_match"
down_revision = "add_wrestlemania"

from alembic import op


def upgrade():
    op.drop_constraint("uq_one_pick_per_match", "wrestlemania_picks", type_="unique")
    op.create_unique_constraint(
        "uq_one_pick_per_outcome", "wrestlemania_picks", ["player_id", "outcome_id"]
    )


def downgrade():
    op.drop_constraint("uq_one_pick_per_outcome", "wrestlemania_picks", type_="unique")
    op.create_unique_constraint(
        "uq_one_pick_per_match", "wrestlemania_picks", ["player_id", "match_id"]
    )
