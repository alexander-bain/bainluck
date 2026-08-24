"""The teams-FTS gate must stay red-first and must stay bound to the live route.

Two failure modes this guards, both of which have already happened once each in
this program:

1. **A gate that passes on a no-op.** LAT-P085 pre-registered "exec_ms < 50 on
   all four RED terms" against a banked red of 386-485 ms. Measured 2026-08-24
   with no index in production at all: 46.6-54.3 ms. The criterion passed on an
   unindexed database. Any future edit that reintroduces an absolute-millisecond
   budget must break a test, not sail through review.

2. **A predicate that drifts away from the index.** LAT-P086 found LAT-P085's
   proposed altnames index used `::text` while the route emits
   `CAST(... AS VARCHAR)`. Postgres matches expression indexes STRUCTURALLY, so
   that index would have built valid and been silently unusable forever. The gate
   compiles its SQL from `_build_team_search_filter`; these tests assert it still
   does, because a hand-pasted copy would keep passing against an index the route
   no longer matches.

Nothing here touches production — the gate's network calls are not exercised.
"""

import importlib.util
import os

import pytest

_GATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "gate_teams_fts_index.py",
)


def _load_gate():
    spec = importlib.util.spec_from_file_location("gate_teams_fts_index", _GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


class TestPredicateIsCompiledFromTheRoute:
    def test_fts_sql_uses_all_three_indexed_columns(self, gate):
        sql = gate._fts_sql("yankees")
        assert "teams.name" in sql
        assert "teams.abbreviation" in sql
        assert "teams.alternate_names" in sql

    def test_altnames_cast_matches_the_route_not_the_p085_proposal(self, gate):
        """LAT-P086's correction, pinned.

        The route casts `alternate_names` to VARCHAR. An index built on `::text`
        is a structurally different expression and would never be used.
        """
        sql = gate._fts_sql("yankees").upper()
        assert "CAST(TEAMS.ALTERNATE_NAMES AS VARCHAR)" in sql

    def test_fts_sql_is_a_websearch_tsquery_match(self, gate):
        sql = gate._fts_sql("red sox").lower()
        assert "to_tsvector" in sql
        assert "websearch_to_tsquery" in sql
        assert "@@" in sql

    def test_control_is_on_a_column_the_ddl_does_not_index(self, gate):
        """The control must be unservable by `ix_teams_fts_*`, or it moves with
        the FTS arm when the DDL lands and the ratio never collapses."""
        control = gate._control_sql("yankees")
        assert "teams.slug" in control
        for column in ("teams.name", "teams.abbreviation", "teams.alternate_names"):
            assert column not in control

    def test_control_is_cpu_matched_not_a_cheap_scan(self, gate):
        """A `count(*) WHERE id > 0` control was rejected: it holds flat at
        ~5.5 ms through a 6x CPU excursion that moves the FTS arm, so it cancels
        none of the noise it is there to cancel. The control must build a
        tsvector per row, like the thing it controls for."""
        control = gate._control_sql("yankees").lower()
        assert "to_tsvector" in control
        assert "websearch_to_tsquery" in control


class TestBudgetIsARatioNotMilliseconds:
    def test_threshold_is_a_ratio_well_below_the_unindexed_floor(self, gate):
        """Observed unindexed ratios 2026-08-24, across a 160-423 ms excursion:
        0.87 1.05 1.09 1.12 1.17 1.24 1.30 1.31 1.32 1.37 1.42 1.57.

        The threshold must sit far enough below that floor that no load swing
        reaches it, and far enough above the post-index expectation (~0.05) to
        not be brittle."""
        assert 0.0 < gate.RATIO_THRESHOLD < 0.87 / 3

    def test_no_absolute_millisecond_budget_survives_in_the_gate(self, gate):
        """The rejected criterion, kept rejected. Any module-level constant whose
        name says milliseconds and whose value is in the 20-500 range is an
        absolute budget sneaking back in."""
        for name, value in vars(gate).items():
            if name.startswith("_") or not isinstance(value, (int, float)):
                continue
            if isinstance(value, bool):
                continue
            assert not (
                name.upper().endswith(("_MS", "_MS_BUDGET", "_MILLIS"))
                and 20 <= value <= 500
            ), f"{name}={value} looks like the absolute budget LAT-P087 removed"


class TestShapeCriterion:
    def test_all_three_indexes_are_required(self, gate):
        assert set(gate.EXPECTED_INDEXES) == {
            "ix_teams_fts_name",
            "ix_teams_fts_abbrev",
            "ix_teams_fts_altnames",
        }

    def test_two_of_three_indexes_is_a_fail(self, gate):
        """A structurally-mismatched third index builds valid and is never used.
        Partial adoption must read as FAIL, not as 'mostly working'."""
        plan = {
            "plan": [
                {
                    "Plan": {
                        "Node Type": "BitmapOr",
                        "Plans": [
                            {"Node Type": "Bitmap Index Scan", "Index Name": "ix_teams_fts_name"},
                            {"Node Type": "Bitmap Index Scan", "Index Name": "ix_teams_fts_abbrev"},
                        ],
                    }
                }
            ]
        }
        used = gate._index_scans(plan)
        missing = [n for n in gate.EXPECTED_INDEXES if n not in used]
        assert missing == ["ix_teams_fts_altnames"]
        assert gate._has_bitmap_or(plan) is True

    def test_a_seq_scan_plan_finds_no_indexes(self, gate):
        plan = {"plan": [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "teams"}}]}
        assert gate._index_scans(plan) == set()
        assert gate._has_bitmap_or(plan) is False

    def test_all_three_present_passes_shape(self, gate):
        plan = {
            "plan": [
                {
                    "Plan": {
                        "Node Type": "BitmapOr",
                        "Plans": [
                            {"Node Type": "Bitmap Index Scan", "Index Name": name}
                            for name in gate.EXPECTED_INDEXES
                        ],
                    }
                }
            ]
        }
        assert gate._index_scans(plan) == set(gate.EXPECTED_INDEXES)
        assert gate._has_bitmap_or(plan) is True


class TestHarnessFailuresAreNotVerdicts:
    def test_missing_execution_time_exits_2_not_1(self, gate):
        """Gotcha #54's amendment: 1 is a result, anything else is a story about
        the harness. An analyze that did not run must never read as RED."""
        with pytest.raises(SystemExit) as exc:
            gate._exec_ms({"plan": [{"Plan": {"Node Type": "Seq Scan"}}]})
        assert exc.value.code == 2

    def test_exec_ms_parses_a_real_payload(self, gate):
        plan = {"plan": [{"Plan": {"Node Type": "Seq Scan"}, "Execution Time": 389.412}]}
        assert gate._exec_ms(plan) == pytest.approx(389.412)


class TestBaselineIsIntact:
    def test_baseline_file_exists_and_carries_the_red_terms(self, gate):
        import json

        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        for term in ("yankees", "celtics", "red sox", "world cup"):
            assert term in baseline
            assert "ids" in baseline[term]
