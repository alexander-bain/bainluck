"""Guard tests for the resolution authority ladder (#845).

These are the CI guard the issue asks for: they FAIL if a change would let a
lower-authority source overwrite a higher one, introduce a new guess-family
write, add an unclassified resolution_source, or drift one of the (previously
copy-pasted) guess-family SQL lists away from the single canonical constant.
"""

import re
from pathlib import Path

import pytest

from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    AUTHORITATIVE_SOURCES_SQL,
    DETERMINISTIC_SOURCES,
    GUESS_FAMILY_SOURCES,
    KNOWN_SOURCES,
    OVERWRITABLE_WINNER_SOURCES,
    OVERWRITABLE_WINNER_SOURCES_SQL,
    SINGLE_WINNER_GUESS_SOURCES,
    SINGLE_WINNER_GUESS_SOURCES_SQL,
    TERMINAL_SOURCES,
    authority_tier,
    is_authoritative,
    is_downgrade,
    is_guess_family,
)

_BACKFILL = Path(__file__).resolve().parents[1] / "app" / "tasks" / "backfill_winners.py"


class TestLadderOrdering:
    def test_tiers_are_strictly_ordered(self):
        for a in AUTHORITATIVE_SOURCES:
            for d in DETERMINISTIC_SOURCES:
                assert authority_tier(a) > authority_tier(d)
        for d in DETERMINISTIC_SOURCES:
            for t in TERMINAL_SOURCES:
                assert authority_tier(d) > authority_tier(t)
        for t in TERMINAL_SOURCES:
            for g in GUESS_FAMILY_SOURCES:
                assert authority_tier(t) > authority_tier(g)

    def test_guess_family_is_lowest(self):
        assert all(authority_tier(g) == 0 for g in GUESS_FAMILY_SOURCES)

    def test_none_and_unknown_below_all(self):
        assert authority_tier(None) == -1
        assert authority_tier("") == -1
        assert authority_tier("some_source_that_does_not_exist") == -1

    def test_tiers_are_disjoint(self):
        sets = [AUTHORITATIVE_SOURCES, DETERMINISTIC_SOURCES, TERMINAL_SOURCES, GUESS_FAMILY_SOURCES]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                assert not (sets[i] & sets[j]), f"overlap between tier sets {i},{j}"


class TestDowngradeGuard:
    def test_guess_cannot_overwrite_authoritative(self):
        # The exact #754 poisoning: a guess over api_settlement is a downgrade.
        assert is_downgrade("api_settlement", "pass2_guess")
        assert is_downgrade("api_settlement", "multi_max_prob")
        assert is_downgrade("box_score", "pass2_guess")
        assert is_downgrade("clean_resolution", "pass2_guess")

    def test_upgrade_and_same_tier_allowed(self):
        # api settlement over a guess is an UPGRADE — not a downgrade.
        assert not is_downgrade("pass2_guess", "api_settlement")
        assert not is_downgrade("clean_resolution", "box_score")
        # same tier re-write is allowed (re-running api_settlement)
        assert not is_downgrade("api_settlement", "clob_authoritative")

    def test_writing_over_unresolved_never_downgrade(self):
        assert not is_downgrade(None, "pass2_guess")
        assert not is_downgrade("", "multi_max_prob")

    def test_helpers(self):
        assert is_guess_family("pass2_guess") and not is_guess_family("api_settlement")
        assert is_authoritative("api_settlement") and not is_authoritative("pass2_guess")


class TestCanonicalSqlFragment:
    def test_overwritable_sql_matches_constant(self):
        assert OVERWRITABLE_WINNER_SOURCES_SQL == (
            "('pass2_guess', 'binary_higher_wins', 'multi_max_prob', "
            "'clean_resolution', 'pass2_loser', 'pass3_threshold')"
        )

    def test_overwritable_set_is_the_historical_tuple(self):
        # Byte-for-byte the tuple that was duplicated across the phases, so the
        # rewiring is behavior-preserving.
        assert OVERWRITABLE_WINNER_SOURCES == (
            "pass2_guess", "binary_higher_wins", "multi_max_prob",
            "clean_resolution", "pass2_loser", "pass3_threshold",
        )

    def test_authoritative_sql_covers_the_tier_and_includes_api_settlement(self):
        # #845 batch 2: the api_settlement write-guards route through this set.
        # It must contain api_settlement (back-compat with the old guard) and the
        # rest of the tier (the hardening), rendered deterministically.
        assert AUTHORITATIVE_SOURCES_SQL.startswith("(") and AUTHORITATIVE_SOURCES_SQL.endswith(")")
        for s in AUTHORITATIVE_SOURCES:
            assert f"'{s}'" in AUTHORITATIVE_SOURCES_SQL
        assert "'api_settlement'" in AUTHORITATIVE_SOURCES_SQL


class TestSingleWinnerGuessSet:
    """#997: the both-winner correction flips ONLY single-winner guesses."""

    def test_is_subset_of_guess_family(self):
        assert set(SINGLE_WINNER_GUESS_SOURCES) <= GUESS_FAMILY_SOURCES

    def test_all_are_tier_zero(self):
        assert all(authority_tier(s) == 0 for s in SINGLE_WINNER_GUESS_SOURCES)

    def test_pass3_threshold_is_excluded(self):
        # The safety crux: pass3_threshold grades cumulative-threshold ladders
        # (Over 3.5 AND Over 4.5 both YES). It is a guess-family member but MUST
        # NOT be flipped by the both-winner correction, or legit ladders break.
        assert "pass3_threshold" in GUESS_FAMILY_SOURCES
        assert "pass3_threshold" not in SINGLE_WINNER_GUESS_SOURCES

    def test_sql_renders_the_three_single_winner_guesses(self):
        assert SINGLE_WINNER_GUESS_SOURCES_SQL == (
            "('pass2_guess', 'binary_higher_wins', 'multi_max_prob')"
        )
        assert "pass3_threshold" not in SINGLE_WINNER_GUESS_SOURCES_SQL


class TestBackfillSourceGuards:
    """Scan the backfill task source — the actual drift/poisoning guard."""

    def _src(self) -> str:
        return _BACKFILL.read_text()

    def test_both_winner_flip_excludes_pass3_threshold_ladders(self):
        # The both-winner correction must flip the guess side via the
        # SINGLE_WINNER_GUESS set (pass3_threshold excluded) and require the
        # sibling to be a NON-guess winner via the full GUESS_FAMILY set. If the
        # function ever hardcodes its own list or drops the sibling guard it
        # could demote a legit cumulative-threshold ladder — this pins the wiring.
        src = self._src()
        assert "_correct_both_winner_guess_side" in src
        assert "SINGLE_WINNER_GUESS_SOURCES_SQL" in src
        # the sibling exclusion must use the FULL guess family (incl. pass3)
        assert "GUESS_FAMILY_SOURCES_SQL" in src

    def test_flat_placeholder_demotion_requires_converged_sibling(self):
        # Queue #167 Item 2 (#999): the "tennis shape" second pass demotes flat-1.0
        # placeholder co-winners (opening=1.0, current≈1.0 that never moved) in mex
        # winner-partition markets — but ONLY when a genuinely-converged winner
        # (opening < 0.9 → current ≥ 0.9) also exists, so a real champion always
        # survives (gotcha #21). Pin the safety gate and the read-side/no-reresolve
        # guarantees so a later edit can't strip them.
        src = self._src()
        assert "placeholder_flipped" in src
        # The degenerate signature: a flat, never-moved opening.
        assert "u.opening_probability = 1.0" in src
        # The survivor gate: a converged sibling winner must exist.
        assert "o.opening_probability < 0.9" in src
        assert "o.current_probability >= 0.9" in src
        # Only the is_winner flag flips — resolution_source is never rewritten and
        # no new winner is asserted (mirrors the guess-side pass).
        assert "SET is_winner = false" in src

    def test_no_hardcoded_guess_family_tuple_remains(self):
        # After rewiring, the guess-family tuple literal must NOT appear inline —
        # every occurrence must interpolate OVERWRITABLE_WINNER_SOURCES_SQL. This
        # is what stops a phase from silently drifting its own list (the #754
        # root cause). If this fails, route the new list through the constant.
        src = self._src()
        offenders = re.findall(
            r"'pass2_guess'\s*,\s*'binary_higher_wins'\s*,\s*'multi_max_prob'",
            src,
        )
        assert offenders == [], (
            f"{len(offenders)} inline guess-family tuple(s) remain in "
            "backfill_winners.py — route them through "
            "resolution_authority.OVERWRITABLE_WINNER_SOURCES_SQL"
        )

    def test_no_bare_api_settlement_write_guard_remains(self):
        # #845 batch 2: the `!= 'api_settlement'` write-guards must route through
        # AUTHORITATIVE_SOURCES_SQL so a phase protects the whole authoritative
        # tier, not just api_settlement. A new bare guard re-opens the clobber gap.
        src = self._src()
        offenders = re.findall(r"!=\s*'api_settlement'", src)
        assert offenders == [], (
            f"{len(offenders)} bare `!= 'api_settlement'` write-guard(s) remain — "
            "route them through NOT IN AUTHORITATIVE_SOURCES_SQL"
        )

    def test_every_written_source_is_classified(self):
        # Completeness guard: every resolution_source the task assigns must be in
        # the ladder, so authority_tier can never silently return -1 for a real
        # write. Adding a new source forces a deliberate ladder classification.
        src = self._src()
        assigned = set(
            re.findall(r"resolution_source\s*=\s*['\"]([a-z0-9_]+)['\"]", src)
        )
        # Non-write helper strings that appear as assignments but are DB markers
        # already covered by the ladder; anything truly new trips this.
        unclassified = {s for s in assigned if s not in KNOWN_SOURCES}
        assert not unclassified, (
            f"resolution_source(s) written but not classified in the authority "
            f"ladder: {sorted(unclassified)} — add them to resolution_authority.py"
        )
