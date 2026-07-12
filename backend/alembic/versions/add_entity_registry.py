"""A1 (#1020) — Entity registry: entities + entity_aliases (identity graph L0)

Creates the universal identity-graph store: one ``entities`` table (kinds:
team / person / event_concept / competition) with first-class date-window
signal columns, and a typed, provenance-tagged ``entity_aliases`` table. Pure
DDL — the teams/competitions fold-in seed runs idempotently in Python
(``app.services.entity_registry.seed_from_teams`` / ``seed_competitions_from_sports``)
so ``alias_norm`` stays byte-identical with the read path's normalization
(a raw-SQL seed would diverge on diacritics without the unaccent extension).

No CREATE INDEX CONCURRENTLY (gotcha #31 — release-phase timeout); the new
tables start empty so plain index creation is instant.

Revision ID: add_entity_registry
Revises: add_disc_cand_snap
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_entity_registry"
down_revision = "add_disc_cand_snap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("slug", sa.String(length=300), nullable=True),
        sa.Column(
            "sport_id",
            sa.Integer(),
            sa.ForeignKey("sports.id"),
            nullable=True,
        ),
        sa.Column("sport_key", sa.String(length=50), nullable=True),
        sa.Column(
            "source_team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("date_window_start", sa.Date(), nullable=True),
        sa.Column("date_window_end", sa.Date(), nullable=True),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column(
            "entity_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("confidence", sa.Numeric(3, 2), server_default="1.0", nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_entities_kind", "entities", ["kind"])
    op.create_index("ix_entities_canonical_name", "entities", ["canonical_name"])
    op.create_index("ix_entities_slug", "entities", ["slug"])
    op.create_index("ix_entities_sport_id", "entities", ["sport_id"])
    op.create_index("ix_entities_sport_key", "entities", ["sport_key"])
    op.create_index("ix_entities_source_team_id", "entities", ["source_team_id"])
    op.create_index("ix_entities_date_window_start", "entities", ["date_window_start"])
    op.create_index("ix_entities_external_ref", "entities", ["external_ref"])
    op.create_index("ix_entities_kind_sport_key", "entities", ["kind", "sport_key"])
    op.create_index(
        "ix_entities_date_window",
        "entities",
        ["date_window_start", "date_window_end"],
    )

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=300), nullable=False),
        sa.Column("alias_norm", sa.String(length=300), nullable=False),
        sa.Column("alias_type", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), server_default="1.0", nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "entity_id",
            "alias_norm",
            "alias_type",
            "source",
            name="uq_entity_alias_norm_type_source",
        ),
    )
    op.create_index("ix_entity_aliases_entity_id", "entity_aliases", ["entity_id"])
    op.create_index("ix_entity_aliases_alias_norm", "entity_aliases", ["alias_norm"])
    op.create_index("ix_entity_aliases_source", "entity_aliases", ["source"])
    op.create_index(
        "ix_entity_aliases_norm_type", "entity_aliases", ["alias_norm", "alias_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_entity_aliases_norm_type", table_name="entity_aliases")
    op.drop_index("ix_entity_aliases_source", table_name="entity_aliases")
    op.drop_index("ix_entity_aliases_alias_norm", table_name="entity_aliases")
    op.drop_index("ix_entity_aliases_entity_id", table_name="entity_aliases")
    op.drop_table("entity_aliases")

    op.drop_index("ix_entities_date_window", table_name="entities")
    op.drop_index("ix_entities_kind_sport_key", table_name="entities")
    op.drop_index("ix_entities_external_ref", table_name="entities")
    op.drop_index("ix_entities_date_window_start", table_name="entities")
    op.drop_index("ix_entities_source_team_id", table_name="entities")
    op.drop_index("ix_entities_sport_key", table_name="entities")
    op.drop_index("ix_entities_sport_id", table_name="entities")
    op.drop_index("ix_entities_slug", table_name="entities")
    op.drop_index("ix_entities_canonical_name", table_name="entities")
    op.drop_index("ix_entities_kind", table_name="entities")
    op.drop_table("entities")
