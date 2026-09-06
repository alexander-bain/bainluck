"""The event graph's closed vocabularies fail closed. #2927 Phase 1.

The database carries the STRUCTURAL rules (a `contains` edge has a class, a
node does not contain itself, confidence is a probability). It deliberately
does not carry the VALUE rules, because a Postgres ENUM makes adding a kind a
migration and this vocabulary is expected to grow. That trade is only safe if
the Python side actually refuses an unknown value, which is what this file is
for.

The precedent is `events.status`: a denylist admits every state nobody thought
of, and there it rejected the rare terminal value (`completed`, 15,731 rows)
while admitting the dominant one (`closed`, 212,289). It read as working for a
year. Every set in `container_graph` is an allowlist; these tests are what say
so.
"""

import pytest

from app.utils import container_graph as cg


class TestFailsClosed:
    """An unknown value RAISES. It is never coerced, defaulted or dropped."""

    @pytest.mark.parametrize(
        "validator,good,bad",
        [
            (cg.validate_container_kind, "tournament", "tourney"),
            (cg.validate_container_status, "final", "completed"),
            (cg.validate_anchor_id_kind, "series", "ticker"),
            (cg.validate_anchor_provider, "espn", "espn_api"),
            (cg.validate_edge_source, "register", "registry"),
            (cg.validate_participant_side, "home", "host"),
            (cg.validate_participant_entity_type, "player", "athlete"),
        ],
    )
    def test_good_passes_and_near_miss_raises(self, validator, good, bad):
        assert validator(good) == good
        with pytest.raises(cg.ContainerVocabularyError):
            validator(bad)

    def test_the_error_names_the_field_and_the_value(self):
        """An error that says only "invalid" sends the reader to the wrong file."""
        with pytest.raises(cg.ContainerVocabularyError) as exc:
            cg.validate_container_kind("tourney")
        message = str(exc.value)
        assert "kind" in message and "tourney" in message

    def test_empty_string_and_none_are_not_quietly_allowed(self):
        for bad in ("", None):
            with pytest.raises((cg.ContainerVocabularyError, TypeError)):
                cg.validate_container_kind(bad)

    def test_case_is_not_normalised_away(self):
        """`Tournament` is not `tournament`.

        Normalising case here would be a kindness that hides a real bug: a
        caller writing `Tournament` is a caller reading a value from somewhere
        we did not expect, and the second value that arrives from that source
        will not be a case variant.
        """
        with pytest.raises(cg.ContainerVocabularyError):
            cg.validate_container_kind("Tournament")


class TestContainsRequiresAClass:
    """The pair rule, tested as a pair — because that is what it is."""

    def test_contains_without_a_class_is_refused(self):
        with pytest.raises(cg.ContainerVocabularyError) as exc:
            cg.validate_edge_kind_and_class("contains", None)
        # The message must point at the answer, not just the problem: the
        # reason this rule exists is that the tempting fix is a NULL class.
        assert cg.CLASS_UNCLASSIFIED in str(exc.value)

    def test_unclassified_is_a_real_answer_and_is_accepted(self):
        """The half that stops the rule becoming a silent loss.

        If `unclassified` were refused, a member assembly could not classify
        would have to be given a wrong class or dropped. Both are the failure
        this program exists to end.
        """
        assert cg.validate_edge_kind_and_class(
            "contains", cg.CLASS_UNCLASSIFIED
        ) == ("contains", cg.CLASS_UNCLASSIFIED)

    def test_unclassified_is_in_the_class_set(self):
        assert cg.CLASS_UNCLASSIFIED in cg.EDGE_CLASSES

    def test_an_unknown_class_on_a_contains_edge_is_refused(self):
        with pytest.raises(cg.ContainerVocabularyError):
            cg.validate_edge_kind_and_class("contains", "doubles_match")

    def test_every_named_class_is_accepted(self):
        for edge_class in cg.EDGE_CLASSES:
            assert cg.validate_edge_kind_and_class("contains", edge_class) == (
                "contains",
                edge_class,
            )

    def test_a_class_on_a_non_contains_edge_is_refused(self):
        """A class on `same_as` is a section assignment nobody will read,
        sitting in the one index the hub scans."""
        with pytest.raises(cg.ContainerVocabularyError):
            cg.validate_edge_kind_and_class("same_as", "match_winner")

    @pytest.mark.parametrize("kind", ["same_as", "derived_from", "advances_to"])
    def test_non_contains_kinds_are_fine_with_no_class(self, kind):
        assert cg.validate_edge_kind_and_class(kind, None) == (kind, None)

    def test_an_unknown_kind_is_refused_even_with_a_valid_class(self):
        with pytest.raises(cg.ContainerVocabularyError):
            cg.validate_edge_kind_and_class("belongs_to", "match_winner")


class TestAssemblyMayNotWriteSameAs:
    """Ruling 048 is unchanged by this table, and that is enforced, not prose.

    A `same_as` edge RECORDS a correspondence an anchored id already proved; it
    does not create one. Assembly gathers members and has no anchored proof of
    identity, so the set of kinds it may write is narrower than the set that
    exists — and the narrowing lives in code where a writer will hit it.
    """

    def test_assembly_may_write_contains(self):
        assert "contains" in cg.ASSEMBLY_WRITABLE_KINDS

    def test_assembly_may_not_write_same_as(self):
        assert "same_as" not in cg.ASSEMBLY_WRITABLE_KINDS

    def test_the_writable_set_is_a_strict_subset_of_the_kinds(self):
        assert cg.ASSEMBLY_WRITABLE_KINDS < cg.EDGE_KINDS


class TestConfidence:
    @pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0, "0.75"])
    def test_inside_the_range_is_accepted(self, value):
        assert 0.0 <= cg.validate_confidence(value) <= 1.0

    @pytest.mark.parametrize("value", [-0.001, 1.001, 2, -1, 100])
    def test_outside_the_range_is_refused(self, value):
        with pytest.raises(cg.ContainerVocabularyError):
            cg.validate_confidence(value)

    def test_the_bounds_are_inclusive(self):
        """A `register` edge is confidence 1.0 and must not be refused."""
        assert cg.validate_confidence(1.0) == 1.0
        assert cg.validate_confidence(0.0) == 0.0


class TestNodeTypesResolveToTables:
    """The nightly invariant check reads `EDGE_NODE_TABLES` rather than a
    hand-written CASE, so a new node type cannot be added without the check
    learning about it in the same commit. This test is what enforces that."""

    def test_every_node_type_has_a_table(self):
        assert set(cg.EDGE_NODE_TABLES) == cg.EDGE_NODE_TYPES

    def test_no_table_is_mapped_twice(self):
        tables = list(cg.EDGE_NODE_TABLES.values())
        assert len(tables) == len(set(tables))

    def test_the_tables_are_real(self):
        """Names checked against the ORM, not spelled from memory."""
        from app.services.database import Base
        import app.models.models  # noqa: F401  — registers the mappers

        known = set(Base.metadata.tables)
        for node_type, table in cg.EDGE_NODE_TABLES.items():
            assert table in known, f"{node_type!r} maps to unknown table {table!r}"


class TestTheModuleStaysImportSafe:
    """`app/models/models.py` imports this module at model-definition time, so
    an import back into the app package is a cycle. Same rule `sport_keys.py`
    lives under (gotcha #3), and the same test shape."""

    def test_it_imports_nothing_from_app(self):
        import ast
        import pathlib

        source = pathlib.Path(cg.__file__).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app"), alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # level > 0 is a relative import, which inside app/utils is an
                # app import by another spelling.
                assert node.level == 0, f"relative import: {ast.dump(node)}"
                assert not module.startswith("app"), module
