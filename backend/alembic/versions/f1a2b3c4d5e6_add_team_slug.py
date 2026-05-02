"""Add slug to teams

Revision ID: f1a2b3c4d5e6
Revises: add_user_seen_mkts
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa
import re

revision = "f1a2b3c4d5e6"
down_revision = "add_user_seen_mkts"
branch_labels = None
depends_on = None


def _slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def upgrade():
    op.add_column("teams", sa.Column("slug", sa.String(200), nullable=True))

    conn = op.get_bind()
    teams = conn.execute(sa.text("SELECT id, name FROM teams")).fetchall()

    seen = {}
    for team_id, name in teams:
        slug = _slugify(name)
        if slug in seen:
            sport_row = conn.execute(
                sa.text("SELECT s.key FROM teams t JOIN sports s ON t.sport_id = s.id WHERE t.id = :id"),
                {"id": team_id},
            ).fetchone()
            suffix = sport_row[0].split("_")[-1] if sport_row else str(team_id)
            slug = f"{slug}-{suffix}"
        seen[slug] = team_id
        conn.execute(
            sa.text("UPDATE teams SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": team_id},
        )

    op.create_unique_constraint("uq_teams_slug", "teams", ["slug"])
    op.create_index("ix_teams_slug", "teams", ["slug"])


def downgrade():
    op.drop_index("ix_teams_slug", table_name="teams")
    op.drop_constraint("uq_teams_slug", "teams", type_="unique")
    op.drop_column("teams", "slug")
