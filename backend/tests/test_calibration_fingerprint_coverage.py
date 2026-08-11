"""CAL-P032 — the fingerprint coverage census, now DERIVED rather than hand-kept.

CAL-P031 shipped this census as a hand-maintained map in
``app/utils/calibration_fingerprint_coverage.py``: four hashed roots, three
covered-by-value names, five cross-module holes and thirty-eight same-module
ones, all typed out by a human reading the source. C258's generated artifact
(``scripts/evals/calibration_fingerprint_derived_map``) parses every one of
those facts out of the real ``_main_input_fingerprint`` body, so the hand map
was **deleted** rather than kept "for reference" — two derivations of one fact
is precisely how they drift, and this lane has paid for that repeatedly.

What survives here is the part the artifact cannot express: **the proof that the
hole is real**, taken by value against the live digest rather than argued from
source. The artifact can say ``CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL`` is
uncovered; only this can show the digest sitting still while the emitted SQL
moves underneath it.

Numbers are asserted against the artifact, not restated, so there is exactly one
place they live. The artifact's own both-directions ratchet is
``tests/evals/test_calibration_fingerprint_derived_map.py::test_generated_map_matches_real_source``
— ``derive_map() == frozen()`` fails on one more input AND on one fewer, which is
gotcha #10's lesson (a one-directional baseline becomes silent headroom) applied
without having to hand-maintain either side of it.
"""

from __future__ import annotations

import json

import pytest

from scripts.evals.calibration_fingerprint_derived_map import (
    DEFAULT_MAP,
    FIX_SEQUENCING_NOTE,
)


@pytest.fixture(scope="module")
def artifact() -> dict:
    return json.loads(DEFAULT_MAP.read_text())


class TestTheHoleIsReal:
    """The digest does not move when a cross-module population value changes.

    This is a CHARACTERIZATION test: it asserts what production does TODAY, not
    what it should do. It is deliberately not an xfail and not skipped, because
    the point is that it goes RED the day someone covers the value — forcing the
    census and the sequencing note to be updated in the same commit as the fix.
    A fix that leaves stale documentation behind is this lane's recurring cost.

    Importing the frozen build module to MEASURE its digest is a read, not a
    commit (ruling 009).
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
            "That is the fix landing (ruling 024's combined invalidation window), which "
            "is good. Now regenerate the derived map so the artifact stops listing it as "
            "uncovered, and update FIX_SEQUENCING_NOTE."
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


class TestTheHandMapIsGoneAndTheArtifactIsAuthority:
    def test_the_hand_maintained_module_no_longer_exists(self):
        """Kept "for reference" is how a superseded map keeps getting cited."""
        with pytest.raises(ModuleNotFoundError):
            __import__("app.utils.calibration_fingerprint_coverage")

    def test_the_census_counts_come_from_the_artifact(self, artifact):
        """46 inputs, 3 covered, 43 uncovered — the C258 figures.

        CAL-P030/P031 prose said "3 of 43", reading the UNCOVERED count as the
        total. The lists were right; the sentence was not. Asserting all three
        against one another makes that class of slip impossible to restate.
        """
        assert artifact["input_count"] == 46
        assert len(artifact["covered_by_value"]) == 3
        assert artifact["uncovered_count"] == 43
        assert artifact["uncovered_count"] == artifact["input_count"] - len(
            artifact["covered_by_value"]
        )
        assert (
            artifact["uncovered_sql_shaping"]
            + artifact["uncovered_behavior_or_evidence"]
            == artifact["uncovered_count"]
        )

    def test_the_four_hashed_roots_are_derived_not_declared_here(self, artifact):
        assert sorted(artifact["hashed_roots"]) == [
            "_calibration_population_ctes",
            "_main_futures_sql",
            "_virtual_market_ctes",
            "compute_calibration_payload",
        ]

    def test_the_proven_hole_is_listed_uncovered_and_sql_shaping(self, artifact):
        """The one with production consequences must never lose its entry."""
        row = next(
            r
            for r in artifact["inputs"]
            if r["name"] == "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL"
        )
        assert row["covered_by_value"] is False
        assert row["sql_interpolated"] is True
        assert row["origin"].startswith("app.utils.resolution_authority")
        # The external definition digest is what makes the artifact a tripwire
        # rather than a list: editing the eligible-source list moves this.
        assert row["definition_sha16"]

    def test_the_five_cross_module_holes_are_the_unguarded_tier(self, artifact):
        """Ruling 009 freezes the build module and NOTHING else, so these are
        live today. The other 38 are protected only incidentally, by a freeze
        that is designed to lift (ruling 024's named failure)."""
        cross = sorted(
            r["name"]
            for r in artifact["inputs"]
            if not r["covered_by_value"]
            and not r["origin"].startswith("app.tasks.precompute_calibration")
        )
        assert cross == [
            "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL",
            "CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL",
            "PRICE_DERIVED_SOURCES_SQL",
            "_COVERAGE_RUNG_KEYS",
            "_build_coverage_census",
        ]
        assert len(cross) + 38 == artifact["uncovered_count"]


class TestInterpolationDetectionCoversNonFStringSql:
    """CAL-P032: the build assembles SQL with ``+`` and ``%``, not only f-strings.

    An f-string-only detector under-counted ``uncovered_sql_shaping`` — the
    number that says how many unguarded values shape the population predicate,
    which is the safety-relevant half of the census. Measured against CAL-P031's
    broader detector, it missed exactly one name.
    """

    def test_concatenated_sql_values_are_classified_as_sql_shaping(self, artifact):
        row = next(
            r for r in artifact["inputs"] if r["name"] == "VM_ROSTER_MARKET_INFO_EXTRA"
        )
        assert row["sql_interpolated"] is True
        assert row["impact"] == "sql_shaping"

    def test_the_detector_sees_plus_concatenation(self):
        from scripts.evals.calibration_fingerprint_derived_map import derive_map

        source = (
            "import inspect\n"
            "from app.utils.input_fingerprint import input_fingerprint\n"
            "SHAPER = 'x'\n"
            "def _main_futures_sql():\n"
            "    return 'SELECT ' + SHAPER\n"
            "def compute_calibration_payload(): pass\n"
            "def _calibration_population_ctes(): pass\n"
            "def _virtual_market_ctes(): pass\n"
            "def _main_input_fingerprint():\n"
            "    return input_fingerprint(inspect.getsource(_main_futures_sql))\n"
        )
        row = next(r for r in derive_map(source)["inputs"] if r["name"] == "SHAPER")
        assert row["sql_interpolated"] is True

    def test_a_value_never_placed_in_a_string_is_not_sql_shaping(self):
        from scripts.evals.calibration_fingerprint_derived_map import derive_map

        source = (
            "import inspect\n"
            "from app.utils.input_fingerprint import input_fingerprint\n"
            "THRESHOLD = 3\n"
            "def _main_futures_sql():\n"
            "    return THRESHOLD > 1\n"
            "def compute_calibration_payload(): pass\n"
            "def _calibration_population_ctes(): pass\n"
            "def _virtual_market_ctes(): pass\n"
            "def _main_input_fingerprint():\n"
            "    return input_fingerprint(inspect.getsource(_main_futures_sql))\n"
        )
        row = next(r for r in derive_map(source)["inputs"] if r["name"] == "THRESHOLD")
        assert row["sql_interpolated"] is False
        assert row["impact"] == "behavior_or_evidence"


class TestTheSequencingConstraintSurvivedTheMove:
    """The note is the only thing the artifact cannot carry: WHEN to apply the fix."""

    def test_it_names_both_independently_sufficient_blockers(self):
        assert "ruling 009" in FIX_SEQUENCING_NOTE
        assert "WIPES EVERY BANKED UNIT" in FIX_SEQUENCING_NOTE

    def test_it_names_the_combined_invalidation_window(self):
        """Ruling 024 moved this from "after a publish" to "inside ONE window"."""
        assert "ruling 024" in FIX_SEQUENCING_NOTE
        assert "combined invalidation window" in FIX_SEQUENCING_NOTE

    def test_it_states_the_ordering_that_is_counter_intuitive(self):
        assert "never during a convergence" in FIX_SEQUENCING_NOTE
