"""Allow multiple relation types per team in user_favorites.

Changes UniqueConstraint from (user_id, team_id) to
(user_id, team_id, relation_type) so a team can be both
"local" and "follow" for the same user.

Revision ID: allow_multi_relation
Revises: add_futures_event_id
Create Date: 2026-02-20
"""

from typing import Union

from alembic import op

# revision identifiers
revision: str = "allow_multi_relation"
down_revision: Union[str, None] = "add_futures_event_id"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_constraint("uq_user_team", "user_favorites", type_="unique")
    op.create_unique_constraint(
        "uq_user_team_relation",
        "user_favorites",
        ["user_id", "team_id", "relation_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_team_relation", "user_favorites", type_="unique")
    op.create_unique_constraint(
        "uq_user_team",
        "user_favorites",
        ["user_id", "team_id"],
    )
