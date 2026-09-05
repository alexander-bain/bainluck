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

        🟢 CAL-P156 MOVED THESE TO 55/51 AND THEN MOVED THEM BACK. It added
        ``UNGRADED_LONE_CLAIM_RULE_TEXT`` for a "rung 1b"; CERT-520 blocked the
        rung as dead code and it was removed, so the constant went with it and
        the totals returned to 54/50. Recorded rather than erased: a tripwire
        that only ever ratchets up teaches the next reader that coming back down
        is suspicious, and here it is exactly right.

        CAL-P162 (2026-08-31) takes this to **55**, and ``uncovered_count``
        stands still at 50 because the same queue moved one input in each
        direction:

        * ``NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT`` is new and behaviour-only —
          published rule prose for RULE E's disclosure. Uncovered, correctly, and
          it does NOT touch the sql-shaping pin below.
        * ``MEX_NORMALIZE_THRESHOLD`` moved the other way, from uncovered
          sql-shaping to **covered by value**. It was always interpolated into
          the emitted SQL, but until RULE E it only decided how a row was
          PRICED; it now decides whether a row is PUBLISHED, because it is the
          sum arm of the bundle exclusion. That is the fifth instance of the hole
          ``_main_input_fingerprint``'s own comment describes, and it was closed
          on the deploy that made it curve-shaping — closing it costs a full
          rebuild on any other day.

        CAL-P164 (2026-08-31) takes this to **56** / uncovered **51**, adding
        ``NONEXCLUSIVE_BUNDLE_CELL_COLUMNS`` — the per-cell census column names
        that CAL-P162 emitted and declared to nobody, which is what CERT-626
        blocked. It is uncovered and that is correct, not a new hole:

        * It is DERIVED, by a generator expression, from
          ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS``, which is already
          ``covered_by_value``. It has no independent degree of freedom — it
          cannot change unless its parent does, and its parent invalidates every
          banked unit by value. Covering a derived name would buy nothing and
          cost a rebuild.
        * It is behaviour-only, so ``uncovered_sql_shaping`` stands still at 21
          — the pin below, which is the count with correctness consequences.
        * Covering it directly is barred today anyway: adding an input to
          ``_main_input_fingerprint`` wipes every banked unit, and ruling 024
          puts that in the one combined invalidation window (see
          ``FIX_SEQUENCING_NOTE``).

        CAL-P168 (2026-08-31) takes this to **65** / uncovered **54**, the
        largest single jump in the file's history, and the shape of the jump is
        the thing to read rather than its size. Rank 1 (`polymarket/baseball`,
        K' = R1+R2+R3+M1) added NINE inputs:

        * **six arrive COVERED** — the cell allowlist, R1's exact 0.5000 spike,
          R3's title pattern, and M1's two band edges plus its drift floor. Each
          is interpolated into the emitted SQL by a helper, so hashing the CTE
          builder's source cannot see their values, and each decides WHICH ROWS
          THE CURVE PUBLISHES. They are hashed by value in
          ``_main_input_fingerprint`` on the deploy that creates them, which is
          why ``covered_by_value`` moves 5 -> 11 while nine inputs appear.
        * **two are behaviour-only** — the rule sentence and the temporary-cell
          map. Prose and disclosure copy; they shape nothing and correctly leave
          ``uncovered_sql_shaping`` alone.
        * **one is the cross-module tier** — ``PAIR_SUM_TOLERANCE``, imported
          from the write-side coherence rule so the two halves cannot disagree.
          It IS hashed by value, but ``derive_declared`` only credits names
          defined in this module, so it cannot read as covered. That +1 is
          argued in its own place below, twice.

        The ratchet was not loosened to absorb this: it is a pin, it fired, and
        every one of the nine is accounted for by name.

        CAL-P1002F (2026-09-04, D66) takes this to **66**, and it is the
        cheapest possible shape of a +1: ONE input, ``SUM_ARM_ONLY_EXCLUDED_CELLS``,
        and it arrives **COVERED**. It is interpolated into the emitted SQL by
        ``_calibration_population_ctes`` (so hashing the builder's source cannot
        see its value) and it decides WHICH ROWS THE CURVE PUBLISHES, so it is
        hashed by value in ``_main_input_fingerprint`` on the deploy that creates
        it — the same discipline CAL-P168's six followed. ``covered_by_value``
        therefore moves 11 -> 12 while ``uncovered_count`` **stands still at 54**,
        which is the whole claim: the unguarded surface did not grow.
        """
        assert artifact["input_count"] == 66
        # CAL-P162: 4 -> 5. `MEX_NORMALIZE_THRESHOLD` joined the by-value set on
        # the deploy that made it decide PUBLICATION rather than only pricing.
        # CAL-P164 added no by-value input, so this stands still.
        # CAL-P168: 5 -> 11. Six of rank 1's seven population-shaping constants
        # closed on the deploy that created them; the seventh cannot be credited
        # here because it is cross-module (see the two tests below).
        # CAL-P1002F: 11 -> 12. D66's `SUM_ARM_ONLY_EXCLUDED_CELLS`, closed on
        # the deploy that created it. `uncovered_count` does not move.
        assert len(artifact["covered_by_value"]) == 12
        assert artifact["uncovered_count"] == 54
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

        🟢 **CAL-P162 (2026-08-31) takes this DOWN, 22 -> 21, and that direction
        is the whole point of the pin.** ``MEX_NORMALIZE_THRESHOLD`` is now
        hashed by value in ``_main_input_fingerprint``, so it is no longer an
        uncovered sql-shaping input. Nothing about the detector changed and
        nothing was reclassified to get here — the hole was closed, which is the
        only legitimate way this number falls. The queue also ADDED a
        behaviour-only input in the same commit
        (``NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT``) and it correctly did not
        register here, which is the separation this test exists to enforce,
        demonstrated in both directions at once.

        🔴 **CAL-P168 (2026-08-31) TAKES THIS 21 -> 22, AND THE ARGUMENT IS THAT
        THE ENTRY IS A DETECTOR LIMIT, NOT A HOLE.** Rank 1 (`polymarket/
        baseball`, K' = R1+R2+R3+M1) added SEVEN new SQL-shaping constants —
        the cell allowlist, R1's 0.5000, R2's pair tolerance, R3's name pattern,
        and M1's two band edges plus its drift floor. **Six of the seven were
        closed in the same commit** by hashing them BY VALUE in
        ``_main_input_fingerprint``, which is the only legitimate way this
        number stays flat, and they register here as covered.

        The seventh, ``PAIR_SUM_TOLERANCE``, is hashed by value in exactly the
        same call — but it is IMPORTED from ``app.utils.pair_opening_coherence``,
        and ``derive_declared`` only credits coverage for names in
        ``_module_defs`` (constants defined in the build module). A cross-module
        input therefore CANNOT read as covered no matter how it is hashed. So
        this +1 is the detector's blind spot being counted, and it is counted
        rather than worked around: the test below tracks the cross-module tier
        by name, so the entry is visible there too and nothing is hidden.

        🟢 **AND ONE MISCOUNT WAS REFUSED RATHER THAN ABSORBED.** Writing the
        payload's rule sentence as ``A + " " + B`` moved
        ``NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT`` — a prose sentence — into this
        count, because the detector marks any name beside a string constant in a
        ``+``. That would have made this 23. The prose is joined with
        ``" ".join(...)`` instead and the pin is 22. Note the difference from
        D21's ``BOOKMAKER_CURVE_REDIS_KEY`` above, which was COUNTED and where
        ``.join`` was explicitly called out as hiding: there, the name had to
        reach an operator-facing message and the value really can change the
        published population. Here it is two sentences of documentation being
        concatenated, the value shapes nothing, and the concatenation style was
        an incidental choice — so choosing the other style is not hiding a name
        from a tripwire, it is not putting a non-input in front of one.
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

        CAL-P156 took it to 46 and then back to 45 when CERT-520 blocked the
        rung whose rule text caused the move. The cross-module FIVE never
        changed, which is the clause that carries the meaning here.

        45 -> 46 at CAL-P164 (``NONEXCLUSIVE_BUNDLE_CELL_COLUMNS``). Same
        direction, same reason as CERT-497/502: it is defined in the build
        module, so the FIVE is untouched and this arithmetic is the only thing
        that moves.

        🔴 **CAL-P168 MAKES IT SIX, AND THAT IS THIS TEST'S FIRST REAL EVENT.**
        Every movement recorded above was in the module-local arithmetic while
        "the cross-module FIVE never changed" carried the meaning. Rank 1's R2
        arm reuses ``PAIR_SUM_TOLERANCE`` — the tolerance the WRITE-side pair
        coherence rule already ships — by importing it rather than restating it,
        so that the read-side exclusion and the write-side rule cannot disagree
        about what "the pair sums to 1" means. That is the right call for the
        rule and it is honestly a new member of the unguarded tier: the value
        lives in another module, another queue can change it, and this build's
        published population moves when it does.

        Two things bound the exposure, and neither is a reason to stop counting
        it. It IS hashed by value in ``_main_input_fingerprint``
        (``player_props_pair_tolerance=``), so a change still invalidates every
        banked unit — the detector simply cannot credit cross-module coverage.
        And ``definition_sha16`` is populated for it, so this artifact moves when
        the constant's definition moves, which is what makes the tier a tripwire
        rather than a list. **The tier is now SIX and the name is written here so
        the next reader inherits the fact rather than rediscovering it.**"""
        cross = sorted(
            r["name"]
            for r in artifact["inputs"]
            if not r["covered_by_value"]
            and not r["origin"].startswith("app.tasks.precompute_calibration")
        )
        assert cross == [
            "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL",
            "CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL",
            "PAIR_SUM_TOLERANCE",
            "PRICE_DERIVED_SOURCES_SQL",
            "_COVERAGE_RUNG_KEYS",
            "_build_coverage_census",
        ]
        # The cross-module tier carries a definition digest precisely so that a
        # change to a constant this module does not own still moves the
        # artifact. Asserted for the new entry rather than assumed.
        pair_tolerance = next(
            r for r in artifact["inputs"] if r["name"] == "PAIR_SUM_TOLERANCE"
        )
        assert pair_tolerance["definition_sha16"]
        assert pair_tolerance["origin"].startswith("app.utils.pair_opening_coherence")
        assert len(cross) + 48 == artifact["uncovered_count"]


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
