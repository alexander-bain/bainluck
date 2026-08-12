"""CAL-P047 — the fingerprint coverage census, now CLOSED rather than reported.

CAL-P031 shipped this census as a hand-maintained map: four hashed roots, three
covered-by-value names, five cross-module holes and thirty-eight same-module
ones, typed out by a human reading the source. C258's generated artifact
(``scripts/evals/calibration_fingerprint_derived_map``) parses every one of those
facts out of the real ``_main_input_fingerprint`` body, so the hand map was
**deleted** rather than kept "for reference" — two derivations of one fact is
precisely how they drift.

**CAL-P047 applied the fix** inside ruling 024's combined invalidation window.
The census reads **47 inputs, 46 covered by value, 1 covered by source, 0
uncovered**. This file previously CHARACTERIZED the hole — it asserted that the
digest sat still while the emitted SQL moved underneath it, and said in its own
docstring that it would go red the day someone covered the value, "forcing the
census and the sequencing note to be updated in the same commit as the fix."

That is what happened: six tests here went red on the fix and are inverted below.
Recorded rather than quietly rewritten, because a characterization test that is
edited without saying why is indistinguishable from one that was wrong.

Numbers are asserted against the artifact, not restated, so there is exactly one
place they live. The artifact's own both-directions ratchet is
``tests/evals/test_calibration_fingerprint_derived_map.py::test_generated_map_matches_real_source``
— ``derive_map() == frozen()`` fails on one more input AND on one fewer, which is
gotcha #10's lesson (a one-directional baseline becomes silent headroom).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from scripts.evals.calibration_fingerprint_derived_map import (
    DEFAULT_MAP,
    FIX_SEQUENCING_NOTE,
)


@pytest.fixture(scope="module")
def artifact() -> dict:
    return json.loads(DEFAULT_MAP.read_text())


class TestTheHoleIsClosed:
    """The digest now MOVES when a cross-module population value changes.

    The inverse of this lane's longest-standing characterization test. It is
    still taken by VALUE against the live digest rather than argued from source,
    for the same reason it always was: the artifact can say a name is covered;
    only this can show the digest moving when the value does.
    """

    def test_digest_tracks_the_eligible_sources_value(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        before = pc._main_input_fingerprint()

        # Exactly what a real edit to app/utils/resolution_authority.py does:
        # the SQL fragment expands differently, the source text does not change.
        monkeypatch.setattr(
            pc, "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL", "('a_different_population')"
        )
        after = pc._main_input_fingerprint()

        assert after != before, (
            "The digest did NOT move — CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL has "
            "lost its coverage. This is the CAL-P031 hole reopening: an edit to "
            "the eligible-source list would change the published population while "
            "a resumed beat carried units built under the old one."
        )

    def test_the_changed_value_really_does_reach_the_emitted_sql(self, monkeypatch):
        """Guards the test above from being vacuous.

        If the value never reached the SQL, a moved digest would prove only that
        we hash a string nobody uses.
        """
        from app.tasks import precompute_calibration as pc

        monkeypatch.setattr(
            pc, "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL", "('a_different_population')"
        )
        emitted = pc._calibration_population_ctes()

        assert "a_different_population" in emitted

    @pytest.mark.parametrize(
        "name,replacement",
        [
            ("CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL", "('probe')"),
            ("PRICE_DERIVED_SOURCES_SQL", "('probe')"),
            ("DRAW_AUTHORITY_OUTCOME_NAMES", frozenset({"probe"})),
            ("SOURCE_LIQUIDITY_EXCLUSIONS", {"probe": ("x",)}),
            ("STAGED_UNIT_WINDOW_SAFETY", 0.123456),
            ("_COVERAGE_RUNG_PREDICATES", (("probe", "1=1"),)),
        ],
    )
    def test_every_covered_class_actually_moves_the_digest(
        self, monkeypatch, name, replacement
    ):
        """One representative of each value SHAPE, not just the famous one.

        A str, a frozenset, a dict, a float and a tuple-of-tuples. The shapes are
        the point: ``_canonical_input`` renders each differently, and a renderer
        that silently returned a constant for an unhandled type would leave that
        whole class uncovered while the census reported it green.
        """
        from app.tasks import precompute_calibration as pc

        before = pc._main_input_fingerprint()
        monkeypatch.setattr(pc, name, replacement)

        assert pc._main_input_fingerprint() != before, f"{name} does not reach the digest"


class TestTheDigestIsStableAcrossProcesses:
    """The trap that would have shipped green, and the only test that can see it.

    Three covered inputs are ``frozenset``. ``repr`` of a set iterates in hash
    order and Python randomises string hashing PER PROCESS, so the documented
    idiom (bare f-string interpolation) yields a different digest in every Celery
    worker. The cursor would be read as foreign on every beat and the build could
    never converge.

    A single-process test cannot observe this — every assertion inside one
    interpreter shares one hash seed. So this test spawns interpreters.
    """

    def _digest_under_seed(self, seed: str) -> str:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "import app.tasks.precompute_calibration as pc;"
                "print(pc._main_input_fingerprint())",
            ],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        ).stdout.strip()

    def test_the_digest_is_identical_under_different_hash_seeds(self):
        digests = {self._digest_under_seed(s) for s in ("1", "2", "3")}

        assert len(digests) == 1, (
            "The fingerprint differs between processes. Some input is being "
            "rendered in hash order — almost certainly a set or dict interpolated "
            "directly instead of through _canonical_input. Every beat would "
            "discard the cursor as foreign."
        )

    def test_the_naive_idiom_really_is_unstable(self):
        """Proves the test above is not vacuous.

        If bare interpolation happened to be stable, the guard would pass for the
        wrong reason and ``_canonical_input`` would look like ceremony.
        """
        naive = {
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import app.tasks.precompute_calibration as pc;"
                    "print(f'{pc.DRAW_AUTHORITY_OUTCOME_NAMES}')",
                ],
                capture_output=True,
                text=True,
                check=True,
                env={"PYTHONHASHSEED": s, "PATH": "/usr/bin:/bin"},
            ).stdout.strip()
            for s in ("1", "2", "3", "4")
        }

        assert len(naive) > 1, (
            "Bare frozenset interpolation was stable across seeds — either Python "
            "changed, or this constant is no longer a set. Re-derive whether "
            "_canonical_input is still load-bearing before trusting the guard above."
        )


class TestCanonicalRenderIsOrderIndependent:
    def test_sets_render_sorted_regardless_of_construction_order(self):
        from app.tasks.precompute_calibration import _canonical_input

        a = _canonical_input(frozenset({"b", "a", "c"}))
        b = _canonical_input(frozenset({"c", "b", "a"}))

        assert a == b == "{'a', 'b', 'c'}"

    def test_sequence_order_is_PRESERVED_not_sorted(self):
        """Order is meaning for a sequence — the rung order IS the contract.

        Sorting these would make two different rung orderings hash identically,
        which is the same class of blindness as not hashing them at all.
        """
        from app.tasks.precompute_calibration import _canonical_input

        assert _canonical_input(("b", "a")) != _canonical_input(("a", "b"))

    def test_a_dict_of_sets_is_stable_all_the_way_down(self):
        from app.tasks.precompute_calibration import _canonical_input

        assert _canonical_input({"k": frozenset({"y", "x"})}) == _canonical_input(
            {"k": frozenset({"x", "y"})}
        )


class TestTheHandMapIsGoneAndTheArtifactIsAuthority:
    def test_the_hand_maintained_module_no_longer_exists(self):
        """Kept "for reference" is how a superseded map keeps getting cited."""
        with pytest.raises(ModuleNotFoundError):
            __import__("app.utils.calibration_fingerprint_coverage")

    def test_the_census_counts_come_from_the_artifact(self, artifact):
        """53 inputs, 53 covered, 0 uncovered — CAL-P045/P047 closed it.

        Was 47 / 3 / 44. CAL-P030/P031 prose said "3 of 43", reading the
        UNCOVERED count as the total; asserting all of them against one another
        makes that class of slip impossible to restate. The identity below is
        what does that work, and it is why the pin is not simply ``== 0``.

        47 -> 53 is ruling 011 part (b) arriving in the same window: importing
        the trade-evidence rule added five constants and one callable to the
        input set. **The ratchet caught that unprompted** — the six landed
        UNCOVERED and had to be covered before this test could pass again, which
        is the concrete proof that parts (a) and (b) are one invalidation event
        rather than two changes that happen to ship together.
        """
        covered = len(artifact["covered_by_value"]) + len(artifact["covered_by_source"])

        assert artifact["input_count"] == 53
        assert len(artifact["covered_by_value"]) == 51
        assert len(artifact["covered_by_source"]) == 2
        assert artifact["uncovered_count"] == 0
        assert artifact["uncovered_count"] == artifact["input_count"] - covered
        assert (
            artifact["uncovered_sql_shaping"]
            + artifact["uncovered_behavior_or_evidence"]
            == artifact["uncovered_count"]
        )

    def test_no_input_shapes_the_sql_without_being_hashed(self, artifact):
        """The count with correctness consequences, pinned on its own.

        It was 21 and is now 0. This is the class that can silently change the
        published population, so it keeps its own assertion even at zero —
        a total reaching zero is exactly when a combined pin stops discriminating.
        """
        assert artifact["uncovered_sql_shaping"] == 0

    def test_the_hashed_roots_are_derived_not_declared_here(self, artifact):
        """Four became six: two CALLABLE inputs are hashed by SOURCE.

        ``repr`` of a function is its memory address — stable within a process,
        different in every worker, and indistinguishable from real coverage in
        the census. ``trade_evidence_sql`` is the one that matters most: it
        EMITS SQL into the population statement, so its text can change the shape
        of a banked unit.
        """
        assert sorted(artifact["hashed_roots"]) == [
            "_build_coverage_census",
            "_calibration_population_ctes",
            "_main_futures_sql",
            "_virtual_market_ctes",
            "compute_calibration_payload",
            "trade_evidence_sql",
        ]

    def test_the_formerly_proven_hole_is_now_covered(self, artifact):
        """The one with production consequences must never lose its entry."""
        row = next(
            r
            for r in artifact["inputs"]
            if r["name"] == "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL"
        )
        assert row["covered_by_value"] is True
        assert row["sql_interpolated"] is True
        assert row["origin"].startswith("app.utils.resolution_authority")
        # The external definition digest is what makes the artifact a tripwire
        # rather than a list: editing the eligible-source list moves this.
        assert row["definition_sha16"]

    def test_the_five_cross_module_inputs_are_all_covered_now(self, artifact):
        """These were THE unguarded tier and the reason the fix mattered.

        Ruling 009 froze the build module and nothing else, so the other 42 were
        protected incidentally by a freeze designed to lift. These five were live
        the whole time. The membership is pinned as well as the coverage, so
        dropping one from the census cannot read as closing it.
        """
        cross = {
            r["name"]: (r["covered_by_value"] or r["covered_by_source"])
            for r in artifact["inputs"]
            if not r["origin"].startswith("app.tasks.precompute_calibration")
        }

        assert sorted(cross) == [
            "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL",
            "CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL",
            "PRICE_DERIVED_SOURCES_SQL",
            "TRADE_EVIDENCE_CLASSES",
            "TRADE_EVIDENCE_EVIDENCED_CLASSES",
            "TRADE_EVIDENCE_EXCLUDED_SOURCES",
            "TRADE_EVIDENCE_RULE_TEXT",
            "TRADE_EVIDENCE_TRADED_CLASSES",
            "_COVERAGE_RUNG_KEYS",
            "_build_coverage_census",
            "trade_evidence_sql",
        ]
        assert all(cross.values()), f"uncovered cross-module input: {cross}"

    def test_the_callable_is_covered_by_source_and_NOT_by_value(self, artifact):
        row = next(
            r for r in artifact["inputs"] if r["name"] == "_build_coverage_census"
        )

        assert row["covered_by_source"] is True
        assert row["covered_by_value"] is False, (
            "A function hashed by value hashes its memory address. That reads as "
            "covered here and differs in every worker."
        )


class TestInterpolationDetectionCoversNonFStringSql:
    """CAL-P032: the build assembles SQL with ``+`` and ``%``, not only f-strings.

    An f-string-only detector under-counted ``uncovered_sql_shaping`` — the
    number that says how many unguarded values shape the population predicate.
    Measured against CAL-P031's broader detector, it missed exactly one name.
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


class TestTheDetectorSeesCrossModuleCoverage:
    """CAL-P047: the census could not have observed its own fix.

    ``derive_declared`` built its ``module_names`` from same-module assignments
    only, so a cross-module constant passed by value to ``input_fingerprint`` was
    not recognised as covered. The five cross-module inputs are exactly the tier
    the freeze never protected — so the detector was blind in precisely the place
    where blindness cost something.
    """

    def test_an_imported_constant_passed_by_value_counts_as_covered(self):
        from scripts.evals.calibration_fingerprint_derived_map import derive_declared

        source = (
            "import inspect\n"
            "from app.utils.resolution_authority import IMPORTED_SQL\n"
            "from app.utils.input_fingerprint import input_fingerprint\n"
            "def _main_futures_sql():\n"
            "    return 'SELECT ' + IMPORTED_SQL\n"
            "def compute_calibration_payload(): pass\n"
            "def _calibration_population_ctes(): pass\n"
            "def _virtual_market_ctes(): pass\n"
            "def _main_input_fingerprint():\n"
            "    return input_fingerprint(f'x={IMPORTED_SQL}',"
            " inspect.getsource(_main_futures_sql))\n"
        )
        _roots, values = derive_declared(source)

        assert "IMPORTED_SQL" in values

    def test_a_non_app_import_is_not_treated_as_a_population_input(self):
        """Scope guard: only ``app.*`` names are build inputs.

        Without this the census would grow an entry every time the module
        imported a stdlib name, and the counts would stop meaning anything.
        """
        from scripts.evals.calibration_fingerprint_derived_map import derive_declared

        source = (
            "import inspect\n"
            "from os import sep\n"
            "from app.utils.input_fingerprint import input_fingerprint\n"
            "def _main_futures_sql():\n"
            "    return 'SELECT ' + sep\n"
            "def compute_calibration_payload(): pass\n"
            "def _calibration_population_ctes(): pass\n"
            "def _virtual_market_ctes(): pass\n"
            "def _main_input_fingerprint():\n"
            "    return input_fingerprint(f'x={sep}',"
            " inspect.getsource(_main_futures_sql))\n"
        )
        _roots, values = derive_declared(source)

        assert "sep" not in values


class TestTheSequencingConstraintSurvivedTheFix:
    """The note is the only thing the artifact cannot carry: WHEN to apply the fix.

    It is kept after application because the constraint binds input 48 exactly as
    it bound these — and a note deleted the moment it is first obeyed teaches
    nobody.
    """

    def test_it_names_both_independently_sufficient_blockers(self):
        assert "ruling 009" in FIX_SEQUENCING_NOTE
        assert "WIPES EVERY BANKED UNIT" in FIX_SEQUENCING_NOTE

    def test_it_names_the_combined_invalidation_window(self):
        """Ruling 024 moved this from "after a publish" to "inside ONE window"."""
        assert "ruling 024" in FIX_SEQUENCING_NOTE
        assert "combined invalidation window" in FIX_SEQUENCING_NOTE

    def test_it_states_the_ordering_that_is_counter_intuitive(self):
        assert "never during a convergence" in FIX_SEQUENCING_NOTE

    def test_it_records_that_the_fix_has_been_applied(self):
        """Otherwise the next reader re-plans work that is already done —
        which is the cost CAL-P044 paid finding CAL-P045 had never been written.
        """
        assert "APPLIED" in FIX_SEQUENCING_NOTE
        assert "CAL-P047" in FIX_SEQUENCING_NOTE

    def test_it_carries_the_traps_forward_for_input_48(self):
        assert "_canonical_input" in FIX_SEQUENCING_NOTE
        assert "covered_by_source" in FIX_SEQUENCING_NOTE
