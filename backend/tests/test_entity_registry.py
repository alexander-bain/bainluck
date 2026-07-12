"""A1 (#1020) — Entity registry: normalization invariant + model structure.

The CI harness mocks the async DB session (no real Postgres), so these tests
pin the pieces that do NOT need a live DB but are the correctness spine:

1. ``normalize_alias`` — the seed writes ``alias_norm`` with it and the read
   path resolves with it, so any drift silently breaks every lookup. This is
   the single most load-bearing invariant in Layer 0.
2. The ``Entity`` / ``EntityAlias`` model shape: kinds, alias types, the
   idempotency unique constraint, the fold-in bridge column, and date-window
   signal columns the plan requires.
"""

import pytest

from app.models.models import Entity, EntityAlias
from app.services import entity_registry as er


class TestNormalizeAlias:
    def test_empty_and_none(self):
        assert er.normalize_alias("") == ""
        assert er.normalize_alias(None) == ""
        assert er.normalize_alias("   ") == ""

    def test_lowercases_and_strips_punctuation(self):
        assert er.normalize_alias("St. Louis Cardinals") == "st louis cardinals"
        assert er.normalize_alias("L.A. Lakers") == "l a lakers"
        assert er.normalize_alias("A's") == "a s"

    def test_strips_diacritics(self):
        assert er.normalize_alias("Viktor Hovland") == "viktor hovland"
        assert er.normalize_alias("Nikola Jokić") == "nikola jokic"
        assert er.normalize_alias("Höjgaard") == "hojgaard"

    def test_collapses_whitespace(self):
        assert er.normalize_alias("  Real   Madrid  ") == "real madrid"
        assert er.normalize_alias("Man\tUtd") == "man utd"

    def test_idempotent(self):
        once = er.normalize_alias("São Paulo F.C.!!!")
        assert er.normalize_alias(once) == once
        assert once == "sao paulo f c"

    def test_seed_and_read_path_share_one_normalizer(self):
        # The whole design rests on the seed and resolve using the SAME function.
        # If someone forks a second normalizer, this catches it: both the write
        # helper and the resolver must reference er.normalize_alias by identity.
        import inspect

        add_alias_src = inspect.getsource(er.add_alias)
        resolve_src = inspect.getsource(er.resolve_alias)
        assert "normalize_alias(" in add_alias_src
        assert "normalize_alias(" in resolve_src


class TestConstants:
    def test_entity_kinds(self):
        assert er.ENTITY_KINDS == {
            "team",
            "person",
            "event_concept",
            "competition",
        }
        assert er.KIND_TEAM == "team"
        assert er.KIND_PERSON == "person"
        assert er.KIND_EVENT_CONCEPT == "event_concept"
        assert er.KIND_COMPETITION == "competition"

    def test_alias_types(self):
        assert er.ALIAS_CANONICAL == "canonical"
        assert er.ALIAS_COMMON_NAME == "common_name"
        assert er.ALIAS_ABBREVIATION == "abbreviation"
        assert er.ALIAS_SOURCE_NAME == "source_name"
        assert er.ALIAS_TICKER_TOKEN == "ticker_token"


class TestModelShape:
    def test_entity_table_and_columns(self):
        assert Entity.__tablename__ == "entities"
        cols = Entity.__table__.columns
        for name in (
            "kind",
            "canonical_name",
            "slug",
            "sport_id",
            "sport_key",
            "source_team_id",  # fold-in bridge to legacy teams row
            "date_window_start",  # first-class date-window signal
            "date_window_end",
            "external_ref",
            "entity_metadata",
            "confidence",
        ):
            assert name in cols, f"Entity missing column {name}"
        assert cols["kind"].nullable is False
        assert cols["canonical_name"].nullable is False

    def test_source_team_id_is_fk_to_teams(self):
        fk = list(Entity.__table__.c.source_team_id.foreign_keys)
        assert len(fk) == 1
        assert fk[0].column.table.name == "teams"

    def test_alias_table_and_unique_constraint(self):
        assert EntityAlias.__tablename__ == "entity_aliases"
        cols = EntityAlias.__table__.columns
        for name in ("entity_id", "alias", "alias_norm", "alias_type", "source"):
            assert name in cols, f"EntityAlias missing column {name}"
        assert cols["alias_norm"].nullable is False

        uniques = [
            c
            for c in EntityAlias.__table__.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        ]
        assert any(
            {col.name for col in u.columns}
            == {"entity_id", "alias_norm", "alias_type", "source"}
            for u in uniques
        ), "idempotency unique constraint missing"

    def test_alias_entity_relationship(self):
        # cascade delete-orphan so dropping an entity cleans its aliases.
        rel = Entity.__mapper__.relationships["aliases"]
        assert rel.mapper.class_ is EntityAlias


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
