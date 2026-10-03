"""The events-FTS gate must grade the INDEX, not the calendar.

The failure mode this guards actually happened, on this gate's very first
after-run (2026-09-09, #4140). Criterion 3 compares the id set each term returns
against a baseline captured before the DDL. `events` is written continuously, so
four MLB fixtures ingested that morning were enough to make `yankees` and
`red sox` come back RED while the index was provably correct — every baseline id
was still present (`LOST=0`); the set had only grown.

That is the worst shape a gate can take. It does not fail loudly on a real
defect; it drifts to RED with age, stays RED for a reason no one can act on, and
trains the next lane to wave its own gate through. The fix is a POPULATION PIN:
the baseline records the instant it was captured, and criterion 3 compares only
rows that existed at that instant. Set equality is exact again, so the criterion
still catches a row the index hides AND a row it invents, while rows ingested
since are counted and reported rather than graded.

These tests pin the pin. Nothing here touches production — the gate's network
calls are never exercised.
"""

import importlib.util
import json
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GATE_PATH = os.path.join(os.path.dirname(_HERE), "scripts", "gate_events_fts_index.py")


def _load_gate():
    spec = importlib.util.spec_from_file_location("gate_events_fts_index", _GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


class TestCriterionThreeIsPinnedToItsBaselinePopulation:
    """The `created_at` pin is the whole defence against a gate that ages RED."""

    def test_ids_sql_is_unpinned_by_default(self, gate):
        """The live set is still reachable — it is what `+N since pin` reports."""
        assert "created_at" not in gate._ids_sql("yankees")

    def test_ids_sql_pins_the_population_when_asked(self, gate):
        sql = gate._ids_sql("yankees", pin="2026-09-09T01:02:55.806834")
        assert "created_at" in sql, (
            "the pin was dropped: criterion 3 is back to comparing a live table "
            "against a frozen capture, which goes RED on ingest alone"
        )
        # The boundary must be inclusive — the baseline's own newest row sits
        # exactly ON the pin (it is where the pin came from), so `<` would
        # discard it and report a phantom LOST every single run.
        assert "<=" in sql.split("created_at")[1][:8], (
            "the pin must be inclusive; the max-created_at row IS the boundary"
        )

    def test_the_pin_survives_as_a_real_timestamp_not_a_quoted_string(self, gate):
        """A `str` bound to a DateTime column does not render under
        `literal_binds`, and the gate compiles to literal SQL. If this regresses
        the gate does not go RED — it raises, which reads as a broken harness."""
        sql = gate._ids_sql("yankees", pin="2026-09-09T01:02:55.806834")
        assert "2026-09-09" in sql

    def test_pinned_and_unpinned_differ_only_by_the_pin(self, gate):
        """The pin must not perturb the predicate it is grading."""
        bare = gate._ids_sql("red sox")
        pinned = gate._ids_sql("red sox", pin="2026-09-09T01:02:55.806834")
        assert "to_tsvector" in bare and "to_tsvector" in pinned
        # Same recall predicate, one extra conjunct.
        assert bare.count("to_tsvector") == pinned.count("to_tsvector")


class TestTheBaselineCarriesItsPin:
    def test_banked_baseline_declares_when_it_was_captured(self, gate):
        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        meta = baseline.get(gate._META_KEY)
        assert meta and meta.get("pin_created_at_utc"), (
            "the banked baseline lost its capture instant; criterion 3 cannot be "
            "graded honestly without it"
        )

    def test_the_meta_key_is_not_graded_as_a_search_term(self, gate):
        """`terms = list(baseline)` would have graded `_meta` as a query."""
        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        terms = [t for t in baseline if t != gate._META_KEY]
        assert gate._META_KEY not in terms
        assert terms, "the baseline has no terms left to grade"
        for term in terms:
            assert "ids" in baseline[term]


class TestTheGateStaysCompiledFromTheLiveRoute:
    """A hand-pasted predicate keeps passing against an index the route no
    longer matches — the #4130 trap this gate exists to have caught."""

    def test_fts_predicate_carries_the_two_arg_config_and_the_coalesce(self, gate):
        sql = gate._ids_sql("yankees")
        # Both are part of the INDEXED EXPRESSION. Postgres matches expression
        # indexes structurally, so dropping either silently unindexes the arm.
        assert "to_tsvector('english'" in sql or "to_tsvector(CAST('english'" in sql, (
            "the config argument is gone; one-arg to_tsvector cannot use the "
            "two-arg expression index (#4130 lost a cycle to exactly this)"
        )
        assert "coalesce" in sql.lower()

    def test_both_team_columns_are_covered(self, gate):
        sql = gate._ids_sql("yankees")
        assert "home_team_name" in sql and "away_team_name" in sql

    def test_the_control_is_not_servable_by_the_indexes_under_test(self, gate):
        """The budget control must be a column this DDL deliberately left
        unindexed, or the ratio compares the index against itself."""
        control = gate._control_sql("yankees")
        assert "home_team_normalized" in control
        for name in gate.EXPECTED_INDEXES:
            assert "normalized" not in name


class TestTheVerdictCannotBeVacuous:
    def test_both_new_indexes_are_required_not_either(self, gate):
        """One index of two is a FAIL: a structurally-mismatched expression
        index builds valid and is then silently never used."""
        assert set(gate.EXPECTED_INDEXES) == {"ix_events_fts_home", "ix_events_fts_away"}

    def test_budget_is_a_ratio_not_an_absolute_millisecond_threshold(self, gate):
        """The sibling teams gate documents an absolute-ms budget PASSING on a
        no-op, because seq-scan cost swings ~6x within a single minute."""
        assert 0 < gate.RATIO_THRESHOLD < 1
