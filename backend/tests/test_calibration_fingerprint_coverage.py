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
        """47 inputs, 3 covered, 44 uncovered — the C258 figures, +1 at CAL-P038.

        CAL-P030/P031 prose said "3 of 43", reading the UNCOVERED count as the
        total. The lists were right; the sentence was not. Asserting all three
        against one another makes that class of slip impossible to restate.

        CAL-P038 moved the totals 46/43 -> 47/44 by adding
        ``STAGED_UNIT_WINDOW_SAFETY``, the unit-window margin. The pin is
        deliberately kept as a pin — it is a tripwire, and a tripwire that is
        loosened when it fires is not one. What matters is WHICH number moved:
        ``uncovered_sql_shaping`` is asserted separately below precisely because
        a behaviour-only input must not touch it, and this one does not.

        CAL-P150 (D21, 2026-08-30) moved the totals 47/44 -> 51/48 by adding the
        four ``BOOKMAKER_CURVE_*`` constants: the Redis key the per-bookmaker
        curve arrives under, the two refusal reason codes, and the expected
        magnitude quoted in the refusal text. Three of the four are
        behaviour-only and do not touch the count below. The fourth does, and
        that is argued in its own place rather than here.

        D12 in the same queue added a fifth, ``NONEXCLUSIVE_BUNDLE_EXCLUDED_
        CELLS`` (51 -> 52) — and it is the first addition in this file's history
        that arrives COVERED. It is interpolated into the emitted SQL, so
        hashing the CTE builder's source would not have caught a change to it
        (``inspect.getsource`` hashes the f-string template, not the substituted
        value); it is hashed by value in ``_main_input_fingerprint`` instead.
        That is why ``covered_by_value`` moves 3 -> 4 here while
        ``uncovered_count`` stands still at 48.

        CERT-497/CERT-502 (2026-08-30) added a sixth and a seventh,
        ``_BOOKMAKER_ROW_REQUIRED_KEYS`` and ``BOOKMAKER_CURVE_SOURCE``
        (52 -> 54, uncovered 48 -> 50). Both are behaviour-only, both are
        classified as such, and **neither moves the count below** — which is the
        separation this docstring promises, restored after CERT-502 found the
        first attempt breaking it.

        🔴 CAL-P156 / CERT-514 ADDED AN EIGHTH AND THE TRIPWIRE FIRED: 54 -> 55,
        uncovered 50 -> 51. It is ``UNGRADED_LONE_CLAIM_RULE_TEXT``, the payload
        rule text for Queue 299 rung 1b (the new per-market exclusion for a
        one-outcome market nothing ever graded). Declared here rather than
        absorbed, because a pin that is edited quietly is not a tripwire.

        Why it is the routine case and not a new hole: it is the SEVENTEENTH
        ``*_RULE_TEXT`` constant, and the derived map classifies it identically
        to the other sixteen — ``covered_by_value: false``,
        ``sql_interpolated: false``, ``impact: behavior_or_evidence``,
        ``used_in: ["compute_calibration_payload"]``. It is prose that ships in
        the payload to explain a filter; it never reaches the emitted SQL, so it
        cannot change the published population. **``uncovered_sql_shaping``
        stands still at 22**, which is the separation that actually matters and
        is asserted on its own below. ``covered_by_value`` stands still at 4.

        The rung's SQL is guarded where SQL is guarded — ``_main_futures_sql``
        is a hashed root, so the CTE and its predicates are covered by source
        hashing, not by this list.
        """
        assert artifact["input_count"] == 55
        assert len(artifact["covered_by_value"]) == 4
        assert artifact["uncovered_count"] == 51
        assert artifact["uncovered_count"] == artifact["input_count"] - len(
            artifact["covered_by_value"]
        )
        assert (
            artifact["uncovered_sql_shaping"]
            + artifact["uncovered_behavior_or_evidence"]
            == artifact["uncovered_count"]
        )

    def test_a_behaviour_only_input_does_not_widen_the_sql_shaping_hole(self, artifact):
        """The count with correctness consequences, pinned on its own.

        The totals above move whenever the module gains any named input. This
        one moves only when an input reaches the emitted SQL, which is the only
        class that can silently change the published population — so separating
        them is what stops a routine +1 from being read as "the unguarded
        surface grew".

        🔴 21 -> 22 AT CAL-P150 (D21, 2026-08-30), AND THIS IS A TRIPWIRE BEING
        RAISED, WHICH IS AS SERIOUS AS ONE BEING LOWERED. Read the argument
        before accepting the number.

        The new entry is ``BOOKMAKER_CURVE_REDIS_KEY``. It is NOT SQL — it is
        the Redis key the per-bookmaker curve arrives under — and it is counted
        because the detector marks any module constant interpolated by f-string,
        ``+`` or ``%`` (CAL-P032 widened it past f-strings on purpose), and the
        key is named in the refusal message that exists to tell an operator
        WHICH key is missing. There is no way to put it in that message the
        detector will not see; a ``.join`` or a local alias would hide it, and
        hiding a name from a tripwire is not satisfying one.

        Counting it is defensible on this test's own terms besides. Change the
        key and the build reads a different curve and publishes ~96,026 fewer
        outcomes, which is exactly "an input that changes the published
        population". What it is no longer is SILENT: D21 makes an unresolvable
        key a named refusal on the producer path rather than a shortfall the
        gate can only describe as "the population moved". So it is the first
        member of this count whose failure mode is loud by construction — and it
        should be the last one accepted on that argument without a fresh one.

        The three sibling constants added by the same change
        (``BOOKMAKER_CURVE_ABSENT_REFUSAL``, ``..._UNREADABLE_REFUSAL``,
        ``..._EXPECTED_OUTCOMES``) are behaviour-only, are classified as such,
        and moved the total in the test above and not this one — which is the
        separation that test's docstring promises.

        🔴 CAL-P152 RAISED THIS PIN 22 -> 23 AND **CERT-502 BLOCKED ON IT AS A
        MEASUREMENT-INTEGRITY REGRESSION. THE RAISE IS WITHDRAWN. THE NUMBER IS
        22 AND THE WITHDRAWAL IS RECORDED HERE RATHER THAN REVERTED SILENTLY.**

        The argument offered was that ``_BOOKMAKER_ROW_REQUIRED_KEYS`` can
        quietly move the published population, which is true, and that this made
        it the FRESH argument the paragraph above demands. The cert's answer is
        the right one: *this* count does not mean "can move the population" — the
        docstring above says it moves "only when an input reaches the emitted
        SQL". The constant does not reach SQL, the raising docstring SAID it does
        not reach SQL, and counting it anyway would have left the guard green
        while its category stopped meaning what downstream reviewers read it to
        mean. **A tripwire you widen the definition of is not a tripwire.**

        So the constant is no longer interpolated into the refusal message — the
        message names the offending key and the fixed prose already names the
        curve, so nothing an operator needs was lost — and the detector now
        classifies it, correctly, as behaviour-only. ``BOOKMAKER_CURVE_SOURCE``
        (CERT-502's own repair) was written the same way for the same reason.
        Both move the totals in the test above and neither moves this one.

        🔴 **THE HONEST RESIDUE, LEFT VISIBLE:** the D21 entry that took this pin
        from 21 to 22 has exactly the same problem — ``BOOKMAKER_CURVE_REDIS_KEY``
        is a Redis key, not SQL, and its own paragraph above concedes "It is NOT
        SQL". It is left counted because unwinding it is a separate question
        about the DETECTOR (it cannot distinguish diagnostic interpolation from
        emitted SQL), not about this repair, and quietly lowering a pin while
        being blocked for quietly raising one would be the same error twice.
        CERT-502's fix-sketch names that detector change as the real remedy.
        """
        assert artifact["uncovered_sql_shaping"] == 22

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
        live today. The other 39 are protected only incidentally, by a freeze
        that is designed to lift (ruling 024's named failure).

        The cross-module FIVE is the assertion that carries the meaning and it
        is unchanged; only the in-module remainder moved (38 -> 39 at CAL-P038,
        and 39 -> 43 at CAL-P150 with the four ``BOOKMAKER_CURVE_*``
        constants), which is the direction that costs nothing — an in-module
        input is behind the freeze.

        ⚠️ "Behind the freeze" is doing less work than it did. Ruling 009 has
        now been opened five times in one day (D5, D21, D22, D13, D12), which is
        exactly ruling 024's named failure arriving on schedule: a freeze
        designed to lift is not a protection you can keep spending. The cross-
        module FIVE is still the assertion that carries the meaning.

        43 -> 45 at CERT-497/CERT-502 (``_BOOKMAKER_ROW_REQUIRED_KEYS`` and
        ``BOOKMAKER_CURVE_SOURCE``). Same direction, same reason: both are
        defined in the build module, so the FIVE is untouched and this
        arithmetic is the only thing that moves.

        45 -> 46 at CAL-P156 / CERT-514 (``UNGRADED_LONE_CLAIM_RULE_TEXT``, the
        payload rule text for rung 1b). Same direction, same reason again — it
        is defined in ``app.tasks.precompute_calibration``, so **the cross-module
        FIVE is unchanged**, which is the clause that carries the meaning here.
        Worth stating plainly given the warning above: this is not a sixth hole,
        it is the in-module remainder, and the list below is the assertion to
        read."""
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
        assert len(cross) + 46 == artifact["uncovered_count"]


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
