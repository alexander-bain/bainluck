"""CAL-P031 — what the main build's input fingerprint actually covers.

The digest is a wholesale cursor invalidator: if it fails to move when the
population changes, a resumed generation merges units computed against two
different definitions of the population and publishes them as one curve. That
is ``LATE_ARRIVAL_NOT_INVALIDATED``, the failure the digest exists to prevent.

Three things are pinned here:

1. **The hole is real** — proven against the live digest, by value, not argued
   from source reading.
2. **The known set does not grow** — a fail-on-new ratchet over every
   module-level input the hashed closure reads but the digest does not cover.
3. **The known set does not silently shrink** — gotcha #10's lesson from
   ``typecheck-baseline.json``: a one-directional baseline becomes silent
   headroom. Covering a value must shrink this list in the same commit.

None of this imports the frozen build module's runtime for the AST work — the
util reads it as text. The one test that DOES import it (:class:`TestTheHoleIsReal`)
imports to *measure* the digest, which is a read, not a commit (ruling 009).
"""

import ast

import pytest

from app.utils.calibration_fingerprint_coverage import (
    BUILD_MODULE_PATH,
    COVERED_BY_VALUE,
    CROSS_MODULE,
    HASHED_ROOTS,
    SAME_MODULE,
    SAME_MODULE_KNOWN,
    DigestInput,
    closure_of,
    cross_module_uncovered,
    uncovered_digest_inputs,
    uncovered_from_build_module,
)


class TestTheHoleIsReal:
    """The digest does not move when a cross-module population value changes.

    This is a CHARACTERIZATION test: it asserts what production does TODAY, not
    what it should do. It is deliberately not an xfail and not skipped, because
    the point is that it goes RED the day someone covers the value — forcing the
    allowlist and the hand-off note to be updated in the same commit as the fix.
    A fix that leaves stale documentation behind is this lane's recurring cost.
    """

    def test_digest_is_blind_to_the_eligible_sources_value(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        before = pc._main_input_fingerprint()

        # Exactly what a real edit to app/utils/resolution_authority.py does:
        # the SQL fragment expands differently, the source text does not change.
        monkeypatch.setattr(
            pc, "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL", "('a_different_population')"
        )
        after = pc._main_input_fingerprint()

        assert after == before, (
            "The digest MOVED — someone covered CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL. "
            "That is the fix landing, which is good. Now remove it from CROSS_MODULE in "
            "app/utils/calibration_fingerprint_coverage.py and update FIX_SEQUENCING_NOTE."
        )

    def test_the_changed_value_really_does_reach_the_emitted_sql(self, monkeypatch):
        """Guards the test above from being vacuous.

        If the value never reached the SQL, an unmoved digest would be correct
        rather than a hole, and the test above would pass for the wrong reason.
        """
        from app.tasks import precompute_calibration as pc

        monkeypatch.setattr(
            pc, "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL", "('a_different_population')"
        )
        emitted = pc._calibration_population_ctes()

        assert "a_different_population" in emitted


class TestRatchet:
    """Fail-on-new, and fail-on-silently-fewer."""

    def test_cross_module_set_is_exactly_the_known_set(self):
        observed = set(cross_module_uncovered())

        assert observed == set(CROSS_MODULE), (
            "The set of UNGUARDED cross-module digest inputs changed.\n"
            f"  added:   {sorted(observed - set(CROSS_MODULE))}\n"
            f"  removed: {sorted(set(CROSS_MODULE) - observed)}\n"
            "ADDED means a new value outside the frozen module now shapes the "
            "population without moving the digest — cover it, or pin it with a "
            "reason. REMOVED means it is now covered: delete its CROSS_MODULE "
            "entry in the same commit (gotcha #10 — a one-way baseline is "
            "silent headroom)."
        )

    def test_same_module_set_is_exactly_the_known_set(self):
        observed = {
            name
            for name, ref in uncovered_from_build_module().items()
            if not ref.is_cross_module
        }

        assert observed == SAME_MODULE_KNOWN, (
            "The same-module uncovered set changed.\n"
            f"  added:   {sorted(observed - SAME_MODULE_KNOWN)}\n"
            f"  removed: {sorted(SAME_MODULE_KNOWN - observed)}\n"
            "These are protected only by ruling 009's freeze, which expires."
        )

    def test_covered_values_are_never_reported_as_holes(self):
        observed = uncovered_from_build_module()

        assert not (COVERED_BY_VALUE & set(observed)), (
            "A value hashed BY VALUE in _main_input_fingerprint was reported as "
            "uncovered — the classifier is wrong, not the digest."
        )

    def test_the_proven_hole_is_pinned_and_reasoned(self):
        """The one with production consequences must never lose its entry."""
        assert "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL" in CROSS_MODULE
        assert "resolution_authority" in CROSS_MODULE["CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL"]

    def test_every_cross_module_entry_carries_a_reason(self):
        for name, reason in CROSS_MODULE.items():
            assert reason.strip(), f"{name} is pinned with no reason"
            assert len(reason) > 40, f"{name}'s reason is too thin to act on"


class TestClosure:
    """The closure is the set the digest is measured against."""

    def test_roots_are_in_their_own_closure(self):
        tree = ast.parse("def a(): pass\ndef b(): a()\n")

        assert closure_of(tree, roots=["b"]) == {"a", "b"}

    def test_closure_is_transitive(self):
        tree = ast.parse("def c(): pass\ndef b(): c()\ndef a(): b()\n")

        assert closure_of(tree, roots=["a"]) == {"a", "b", "c"}

    def test_closure_terminates_on_recursion(self):
        tree = ast.parse("def a(): b()\ndef b(): a()\n")

        assert closure_of(tree, roots=["a"]) == {"a", "b"}

    def test_real_closure_reaches_past_the_four_roots(self):
        """If this collapsed to the roots, the whole audit would be vacuous."""
        tree = ast.parse(BUILD_MODULE_PATH.read_text(encoding="utf-8"))
        closure = closure_of(tree)

        assert set(HASHED_ROOTS) <= closure
        assert len(closure) > len(HASHED_ROOTS) + 10


class TestDetection:
    """The classifier itself, on inputs small enough to reason about."""

    def test_detects_a_cross_module_import_used_in_a_root(self):
        source = (
            "from app.utils.resolution_authority import THING\n"
            "def _main_futures_sql():\n"
            "    return f'x {THING}'\n"
        )

        found = uncovered_digest_inputs(source)

        assert found["THING"].module == "app.utils.resolution_authority"
        assert found["THING"].is_cross_module is True
        assert found["THING"].interpolated is True

    def test_detects_a_same_module_constant(self):
        source = "LIMIT = 3\ndef _main_futures_sql():\n    return f'x {LIMIT}'\n"

        found = uncovered_digest_inputs(source)

        assert found["LIMIT"].module == SAME_MODULE
        assert found["LIMIT"].is_cross_module is False

    def test_value_reached_only_through_a_callee_is_still_reported(self):
        """The entire point: getsource covers a function, never its callees."""
        source = (
            "EXCLUDE = 'x'\n"
            "def _helper():\n"
            "    return f'and {EXCLUDE}'\n"
            "def _main_futures_sql():\n"
            "    return 'select ' + _helper()\n"
        )

        found = uncovered_digest_inputs(source)

        assert "EXCLUDE" in found
        assert found["EXCLUDE"].used_in == ("_helper",)

    def test_covered_by_value_names_are_excluded(self):
        source = (
            "COVERAGE_CENSUS_ENABLED = False\n"
            "def _main_futures_sql():\n"
            "    return f'x {COVERAGE_CENSUS_ENABLED}'\n"
        )

        assert "COVERAGE_CENSUS_ENABLED" not in uncovered_digest_inputs(source)

    def test_names_outside_the_closure_are_not_reported(self):
        source = (
            "UNRELATED = 1\n"
            "def _somewhere_else():\n"
            "    return UNRELATED\n"
            "def _main_futures_sql():\n"
            "    return 'x'\n"
        )

        assert "UNRELATED" not in uncovered_digest_inputs(source)

    def test_non_app_imports_are_ignored(self):
        source = (
            "from collections import OrderedDict\n"
            "def _main_futures_sql():\n"
            "    return str(OrderedDict)\n"
        )

        assert "OrderedDict" not in uncovered_digest_inputs(source)

    def test_string_concatenation_counts_as_interpolation(self):
        source = "FRAG = 'a'\ndef _main_futures_sql():\n    return 'select ' + FRAG\n"

        assert uncovered_digest_inputs(source)["FRAG"].interpolated is True

    def test_a_value_never_placed_in_a_string_is_flagged_not_interpolated(self):
        source = "THRESH = 3\ndef _main_futures_sql():\n    return [THRESH]\n"

        found = uncovered_digest_inputs(source)

        assert found["THRESH"].interpolated is False
        assert "THRESH" in found, "still an uncovered input — just not a SQL-shaping one"

    def test_local_variables_are_not_module_level_inputs(self):
        source = "def _main_futures_sql():\n    local_thing = 1\n    return local_thing\n"

        assert uncovered_digest_inputs(source) == {}


class TestRealPopulationValueIsFlagged:
    """End to end against the real module, not a fixture."""

    def test_eligible_sources_is_reported_uncovered_cross_module_interpolated(self):
        found = uncovered_from_build_module()
        ref = found["CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL"]

        assert ref.is_cross_module is True
        assert ref.module == "app.utils.resolution_authority"
        assert ref.interpolated is True
        assert "_calibration_population_ctes" in ref.used_in

    def test_digest_input_is_frozen(self):
        ref = DigestInput(name="X", module=SAME_MODULE, used_in=(), interpolated=False)

        with pytest.raises(Exception):
            ref.name = "Y"  # type: ignore[misc]
