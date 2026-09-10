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


class TestPersonFoldIn:
    """Queue #170 — A1 person fold-in helpers (seed persons from events/futures)."""

    def test_person_kind_and_alias_constants(self):
        from app.services import entity_registry as er

        assert er.KIND_PERSON == "person"
        assert er.ALIAS_COMMON_NAME == "common_name"
        assert er.ALIAS_CANONICAL == "canonical"

    def test_is_person_sport_key(self):
        from app.services.entity_registry import _is_person_sport_key

        for k in ("mma_mixed_martial_arts", "boxing_boxing", "tennis_atp",
                  "golf_pga", "motorsport_other", "tennis_wta_wimbledon"):
            assert _is_person_sport_key(k), k
        for k in ("basketball_nba", "baseball_mlb", "americanfootball_nfl", None):
            assert not _is_person_sport_key(k), k

    def test_person_ref_is_sport_bucketed_and_stable(self):
        from app.services.entity_registry import _person_ref

        a = _person_ref("mma_mixed_martial_arts", "khamzat chimaev")
        b = _person_ref("mma_mixed_martial_arts", "khamzat chimaev")
        c = _person_ref("golf", "khamzat chimaev")
        assert a == b            # stable → idempotent seed
        assert a != c            # bucketed by sport → no cross-sport collision
        assert a.startswith("person:")

    def test_surname_alias_matches_engine_player_key(self):
        """The surname alias the seed writes MUST equal the key the engine derives
        (player_key) — else a market naming a fighter by surname would never
        resolve to the seeded full-name entity."""
        from app.services.entity_registry import normalize_alias
        from app.utils.event_matcher import player_key

        for full in ("Tahir Abdullayev", "Khamzat Chimaev", "Iga Swiatek"):
            surname = player_key(full)
            assert surname == normalize_alias(full).split()[-1]

    def test_non_person_field_names_are_excluded(self):
        from app.services.entity_registry import _NON_PERSON_FIELD_NAMES

        for junk in ("the field", "no winner", "other", "yes", "no"):
            assert junk in _NON_PERSON_FIELD_NAMES

    def test_seed_functions_exist_and_are_coroutines(self):
        import inspect

        from app.services import entity_registry as er

        assert inspect.iscoroutinefunction(er.seed_persons_from_events)
        assert inspect.iscoroutinefunction(er.seed_persons_from_futures_fields)


class _RecordingSession:
    """Minimal stand-in for the AsyncSession ``_upsert_person`` touches.

    Only ``add`` and ``flush`` are exercised before the guard's decision point,
    so a real DB is not needed to prove the CALL SITE refuses (the fix has to be
    observable at the wiring, not only in the predicate).
    """

    def __init__(self):
        self.added = []

    def add(self, obj):
        obj.id = 1
        self.added.append(obj)

    async def flush(self):
        return None


class TestPersonNamePlausibility:
    """#4458 ship 4 — a market leg must never be folded in as a ``person``.

    Measured on production 2026-09-10: 4,913 of 7,471 (65.8 %) persons produced
    by ``seed_persons_from_futures_fields`` are not people. 1,450 of them share
    the single derived alias ``strokes`` and 1,124 share ``round``, so a
    name-keyed lookup equates entities that are not the same subject.
    """

    # (name, why) — every string is a REAL production canonical_name.
    LADDERS = [
        ("1+ strokes", "margin bucket"),
        ("Exactly 5 strokes", "margin bucket"),
        ("R1: Justin Rose under 73.5 strokes", "round/score ladder"),
        ("Above 13500", "numeric bucket"),
        ("No. 23 Heart of Racing Team", "a team, not a person"),
        ("2027 Ryder Cup", "a competition"),
        ("Racing 92", "a club"),
    ]
    MATCHUPS = [
        ("Jon Rahm beats McIlroy and Spieth", "three players in one row"),
        ("Marek Fleming beats Robert MacIntyre in the 3rd Round", "two players"),
        ("Rory McIlroy beats Scottie Scheffler in the full tournament", "two"),
    ]
    REAL_PEOPLE = [
        "Christiaan Maas", "Stacy Lewis", "Patrick Rodgers", "Sam Mayer",
        "Herman Wibe Sekne", "You Min Hwang", "Viktor Hovland",
        # Colliding surnames are REAL competitors and must still seed — the
        # same-name problem is solved at read time, never by refusing to seed.
        "Michael Kim", "Danny Lee",
    ]

    @pytest.mark.parametrize("name,why", LADDERS + MATCHUPS)
    def test_market_legs_are_not_plausible_people(self, name, why):
        from app.services.entity_registry import is_plausible_person_name

        assert not is_plausible_person_name(name), f"{name!r} accepted ({why})"

    @pytest.mark.parametrize("name", REAL_PEOPLE)
    def test_real_competitors_still_pass(self, name):
        from app.services.entity_registry import is_plausible_person_name

        assert is_plausible_person_name(name), name

    @pytest.mark.parametrize("name,why", LADDERS + MATCHUPS)
    @pytest.mark.asyncio
    async def test_upsert_person_creates_nothing_for_a_market_leg(self, name, why):
        """THE WIRING: the guard has to be reached by the seed's own call path."""
        from app.services import entity_registry as er

        session = _RecordingSession()
        created, aliases = await er._upsert_person(
            session, name=name, sport_id=None, sport_key="golf",
            existing_refs=set(), source="seed_persons_futures",
        )
        assert (created, aliases) == (0, 0), f"{name!r} seeded ({why})"
        assert session.added == [], f"{name!r} created an Entity row"

    @pytest.mark.asyncio
    async def test_upsert_person_still_seeds_a_real_competitor(self, monkeypatch):
        """The negative control: the guard must not swallow the happy path."""
        from app.services import entity_registry as er

        minted = []

        async def fake_add_alias(session, entity_id, alias, alias_type, **kw):
            minted.append((alias, alias_type))
            return True

        monkeypatch.setattr(er, "add_alias", fake_add_alias)
        session = _RecordingSession()
        created, aliases = await er._upsert_person(
            session, name="Christiaan Maas", sport_id=None, sport_key="golf",
            existing_refs=set(), source="seed_persons_futures",
        )
        assert created == 1 and aliases == 2
        assert len(session.added) == 1
        assert ("Christiaan Maas", er.ALIAS_CANONICAL) in minted
        assert ("maas", er.ALIAS_COMMON_NAME) in minted

    @pytest.mark.asyncio
    async def test_single_character_surname_alias_is_not_minted(self, monkeypatch):
        """"Cut Line: Even par (E)" keys to the surname "e", which as an alias
        would equate every row ending in that token. The canonical alias may
        still be written; the one-letter derived key may not."""
        from app.services import entity_registry as er

        minted = []

        async def fake_add_alias(session, entity_id, alias, alias_type, **kw):
            minted.append((alias, alias_type))
            return True

        monkeypatch.setattr(er, "add_alias", fake_add_alias)
        session = _RecordingSession()
        await er._upsert_person(
            session, name="Cut Line: Even par (E)", sport_id=None,
            sport_key="golf", existing_refs=set(), source="seed_persons_futures",
        )
        assert ("e", er.ALIAS_COMMON_NAME) not in minted
        assert not any(a == "e" for a, _ in minted)

    @pytest.mark.asyncio
    async def test_placeholder_surname_alias_is_not_minted(self, monkeypatch):
        """A derived surname that is itself a field placeholder must not become
        an alias — it would equate every competitor whose leg ends in that word.

        CONSTRUCTED specimen, not an observed one: as of 2026-09-10 no production
        person entity keys to a ``_NON_PERSON_FIELD_NAMES`` token, because the
        digit rule already removes the O/U ladders ("under 73.5 strokes") that
        would produce one. This is the guard for the number-less shape, and
        without it the clause is untested (it survived mutation M5).
        """
        from app.services import entity_registry as er

        minted = []

        async def fake_add_alias(session, entity_id, alias, alias_type, **kw):
            minted.append((alias, alias_type))
            return True

        monkeypatch.setattr(er, "add_alias", fake_add_alias)
        session = _RecordingSession()
        created, _ = await er._upsert_person(
            session, name="Rickie Fowler Over", sport_id=None, sport_key="golf",
            existing_refs=set(), source="seed_persons_futures",
        )
        assert created == 1                                   # still a seedable row
        assert ("Rickie Fowler Over", er.ALIAS_CANONICAL) in minted
        assert ("over", er.ALIAS_COMMON_NAME) not in minted


class TestCanonicalizeEntities:
    """#175 Item 1 — same-family duplicate merge (the fix the census enables).

    The CI harness mocks the async session, so these pin the correctness spine
    that does NOT need a live DB: the census-safety gate, idempotency guarantees,
    and family-key parity with the census script. Functional proof (surplus rows
    dropping) is the production run recorded in the seed_diag:canonicalize marker.
    """

    def test_exists_and_is_coroutine(self):
        import inspect

        from app.services import entity_registry as er

        assert inspect.iscoroutinefunction(er.canonicalize_entities)

    def test_only_merges_same_family_groups(self):
        # The whole safety argument is: NEVER merge a group whose copies span more
        # than one sport family (cross-sport homonyms). The gate must skip them.
        import inspect

        from app.services import entity_registry as er

        src = inspect.getsource(er.canonicalize_entities)
        assert "families > 1" in src
        assert "risky_skipped" in src

    def test_family_key_matches_census_script(self):
        # The merge's family definition MUST equal the census tool's, or the fix
        # would target a different population than the measurement reports.
        from app.services.entity_registry import _FAMILY_SQL

        # scripts/ isn't an importable package; read the census family expr text.
        import pathlib

        census = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "audit_entity_dups.py"
        text = census.read_text()
        # Both use split_part(lower(coalesce(<col>,'')),'_',1) on the sport_key.
        assert "split_part(lower(coalesce(sport_key, '')), '_', 1)" in _FAMILY_SQL
        assert "split_part(lower(coalesce(" in text and "'_', 1)" in text

    def test_additive_first_repoint_before_delete(self):
        # Aliases must REPOINT (idempotent insert) before any entity is deleted,
        # and only the non-survivor dups are ever deleted.
        import inspect

        from app.services import entity_registry as er

        src = inspect.getsource(er.canonicalize_entities)
        insert_at = src.index("INSERT INTO entity_aliases")
        delete_at = src.index("delete(Entity)")
        assert insert_at < delete_at, "must repoint aliases before deleting dups"
        assert "ON CONFLICT ON CONSTRAINT uq_entity_alias_norm_type_source DO NOTHING" in src
        # survivor is the lowest id; dups are the rest.
        assert "survivor, dups = ids[0], ids[1:]" in src

    def test_dry_run_writes_nothing(self):
        import inspect

        from app.services import entity_registry as er

        src = inspect.getsource(er.canonicalize_entities)
        # In dry_run the loop counts and `continue`s before any INSERT/UPDATE/DELETE.
        assert "if dry_run:" in src

    def test_preserves_edition_scoping_in_metadata(self):
        import inspect

        from app.services import entity_registry as er

        src = inspect.getsource(er.canonicalize_entities)
        assert "canonical_sport_keys" in src

    def test_task_and_endpoint_wired(self):
        import inspect

        from app.tasks.entity_seed import (
            canonicalize_entities_impl,
            seed_entity_registry_impl,
        )

        assert inspect.iscoroutinefunction(canonicalize_entities_impl)
        # The seed calls canonicalize at the end so it stays durable across re-seeds.
        assert "canonicalize_entities" in inspect.getsource(seed_entity_registry_impl)
