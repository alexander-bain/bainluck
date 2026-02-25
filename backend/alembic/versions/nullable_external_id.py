"""Make Event.external_id nullable for StatPal-first event creation.

StatPal schedule sync creates Event records before The Odds API discovers
them. These events start with external_id=NULL. When Odds API finds the
same game, it fills in external_id by matching sport + teams + time.

Revision ID: nullable_external_id
Revises: add_team_identity
"""

from alembic import op


# revision identifiers
revision = "nullable_external_id"
down_revision = "add_team_identity"
branch_labels = None
depends_on = None


def upgrade():
    # Make external_id nullable — StatPal-created events won't have an Odds API ID
    # The existing UNIQUE constraint still works: PostgreSQL allows multiple NULLs
    # in unique columns, so StatPal events don't conflict with each other.
    op.alter_column("events", "external_id", nullable=True)


def downgrade():
    # Restore NOT NULL — first delete any rows with NULL external_id
    op.execute("DELETE FROM events WHERE external_id IS NULL")
    op.alter_column("events", "external_id", nullable=False)
