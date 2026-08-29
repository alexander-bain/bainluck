"""CAL-P127 — guards for the ``golfround`` dimension.

``series`` folds ``kalshi/golf`` into 63 arms. ``calibration_rule_search``
refuses anything past ``MAX_CLASSES`` rather than sampling, so a 63-arm fold
cannot be searched — and the only remaining move is to read the table and pick
the bad-looking rows by hand, which is an exhaustive search for an overfit run
by a human instead of a loop. ``golfround`` exists to collapse those arms onto
the two properties the Kalshi ticker genuinely encodes, so the searcher can do
its job over a 2^6 lattice with a holdout.

Everything that can go wrong with it is silent — a mis-classified series does
not error, it moves rows between two well-formed arms and changes a verdict:

* **Testing ``R`` instead of ``R[0-9]``** pulls ``KXPGAROUNDSCORE`` (679 rows),
  ``KXPGAROUNDLOW`` and ``KXOWGRRANK`` into the round arm. Those are
  tournament-scoped markets and two of them are well calibrated, so the round
  arm's ECE falls and a rule keyed on it looks smaller and safer than it is.
* **Leaving ``TOP[0-9]+$`` unanchored** would let a future ``KXPGATOP10MARGIN``
  join the TOP-N arm. Gotcha #129: an enumeration written by reading one
  source's titles is complete for that source and silently partial for the next.
* **Re-implementing the classification in Python for the tests** would guard a
  paraphrase. Every test below extracts the regex LITERALS out of the SQL that
  actually runs, so the assertion is about the shipped expression.

THE ONE THING THESE TESTS DO NOT PROVE. They run the SQL's regexes through
Python's ``re``, not through Postgres. For the three patterns involved —
``R[0-9]``, ``TOP[0-9]+$``, ``LEAD$`` — POSIX and Python agree: no alternation,
no backreferences, no lazy quantifiers, and ``$`` means end-of-string in both
because the operands are single-line series tokens. A pattern that used any of
those features would have to be measured against the server instead, and
:func:`test_the_patterns_stay_inside_the_agreeing_subset` fails if one appears.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


def _patterns() -> list[str]:
    """The regex literals the shipped ``golfround`` expression compares against."""
    return re.findall(r"~ '([^']+)'", cce.GOLFROUND_EXPR)


def _round_pat() -> str:
    return _patterns()[0]


def _topn_pat() -> str:
    return _patterns()[1]


def _lead_pat() -> str:
    return _patterns()[2]


def classify(series: str) -> str:
    """Apply the SHIPPED patterns in the SHIPPED order."""
    scope = "round" if re.search(_round_pat(), series) else "tourney"
    if re.search(_topn_pat(), series):
        fam = "topn"
    elif re.search(_lead_pat(), series):
        fam = "lead"
    else:
        fam = "other"
    return f"{scope}|{fam}"


#: Every series ticker present in the published ``kalshi/golf`` cell, frozen from
#: ``artifacts/cal-p127/exact-kalshi-golf-series.json`` (population q268,
#: curve 2026-08-29T00:36:47Z). This is the real corpus, not a sample: a
#: classification that is right on invented tickers and wrong on these would
#: still ship a wrong verdict.
REAL_SERIES = [
    "KXCHAMPTOUR", "KXCHESSTOURNAMENT", "KXDPWORLDTOUR", "KXDPWORLDTOURMAKECUT",
    "KXDPWORLDTOURR1LEAD", "KXDPWORLDTOURR2LEAD", "KXDPWORLDTOURR3LEAD",
    "KXITFWMATCH", "KXKFTOUR", "KXLIVH2H", "KXLIVOCCUR", "KXLIVR1LEAD",
    "KXLIVR2LEAD", "KXLIVTOP10", "KXLIVTOP5", "KXLIVTOUR", "KXLPGAR1LEAD",
    "KXLPGAR2LEAD", "KXLPGAR3LEAD", "KXLPGATOUR", "KXOWGRRANK", "KXPBAGAME",
    "KXPGA1STTIMEWIN", "KXPGA3BALL", "KXPGA5BALL", "KXPGAAGECUT", "KXPGABIRDIES",
    "KXPGABOGEYFREE", "KXPGAC", "KXPGACUTLINE", "KXPGAEAGLE", "KXPGAH2H",
    "KXPGAHOLE", "KXPGAHOLEINONE", "KXPGAHOLESCORE", "KXPGALOWSCORE",
    "KXPGAMAJORWIN", "KXPGAMAKECUT", "KXPGAMASTERS", "KXPGAPLAYERCAT",
    "KXPGAPLAYOFF", "KXPGAR1LEAD", "KXPGAR1TOP10", "KXPGAR1TOP20", "KXPGAR1TOP5",
    "KXPGAR2LEAD", "KXPGAR2TOP10", "KXPGAR2TOP5", "KXPGAR3LEAD", "KXPGAR3TOP10",
    "KXPGAR3TOP5", "KXPGAROUNDLOW", "KXPGAROUNDSCORE", "KXPGASTROKEMARGIN",
    "KXPGATOP10", "KXPGATOP20", "KXPGATOP40", "KXPGATOP5", "KXPGATOUR",
    "KXPGAUSO", "KXPGAWINNERREGION", "KXPGAWINNINGSCORE", "KXRT",
]

#: The three tickers that carry an R which is NOT a round number, and the one
#: that carries ROUND as a word. Each is a measured counterexample to the
#: cheaper predicate somebody will eventually propose; none may be removed
#: without a new measurement.
NOT_A_ROUND = {
    "KXPGAROUNDSCORE": "the word ROUND, no round number — 679 rows, ECE 3.02",
    "KXPGAROUNDLOW": "the word ROUND, no round number",
    "KXOWGRRANK": "a doubled R inside RANK, no digit",
    "KXPGAR1LEAD": None,  # the control: this one IS a round
}


class TestTheRoundTestNeedsADigit:
    def test_the_three_false_positives_are_not_round_scoped(self):
        for series, why in NOT_A_ROUND.items():
            if why is None:
                continue
            assert classify(series).startswith("tourney|"), f"{series}: {why}"

    def test_the_control_still_is_round_scoped(self):
        assert classify("KXPGAR1LEAD") == "round|lead"

    def test_a_bare_R_predicate_would_break_all_three(self):
        """SILENT: proves the digit is load-bearing rather than decorative.

        If this ever fails, the cheaper predicate has become equivalent and the
        comment explaining the digit is stale — but so is the reason to trust
        the round arm's number, so it must be re-measured, not deleted.
        """
        broken = [s for s in NOT_A_ROUND if s != "KXPGAR1LEAD" and re.search("R", s)]
        assert len(broken) == 3, "the counterexamples no longer exercise the trap"

    def test_the_shipped_pattern_requires_a_digit(self):
        assert "[0-9]" in _round_pat(), _round_pat()


class TestTheFamilyTestsAreAnchored:
    @pytest.mark.parametrize("pat_fn", [_topn_pat, _lead_pat])
    def test_the_family_patterns_end_anchored(self, pat_fn):
        assert pat_fn().endswith("$"), pat_fn()

    def test_a_suffixed_top_n_ticker_does_not_join_the_topn_arm(self):
        """Gotcha #129 — the enumeration must fail toward 'other', not toward 'topn'."""
        assert classify("KXPGATOP10MARGIN") == "tourney|other"
        assert classify("KXPGAR1TOP10MARGIN") == "round|other"

    def test_a_suffixed_lead_ticker_does_not_join_the_lead_arm(self):
        assert classify("KXPGAR1LEADMARGIN") == "round|other"

    def test_topn_is_tested_before_lead(self):
        """Order matters only if a ticker could match both; assert the order anyway,
        because a future ticker that does would otherwise flip arms silently."""
        assert _topn_pat() in cce.GOLFROUND_EXPR
        assert (cce.GOLFROUND_EXPR.index(_topn_pat())
                < cce.GOLFROUND_EXPR.index(_lead_pat()))


class TestItIsAPartitionOverTheRealCorpus:
    def test_every_real_series_lands_in_exactly_one_named_arm(self):
        arms = {"round", "tourney"}
        fams = {"topn", "lead", "other"}
        for s in REAL_SERIES:
            scope, _, fam = classify(s).partition("|")
            assert scope in arms and fam in fams, s

    def test_the_corpus_actually_exercises_four_arms(self):
        """A partition that collapses to one arm proves nothing about the cell."""
        seen = {classify(s) for s in REAL_SERIES}
        assert {"round|topn", "round|lead", "tourney|topn", "tourney|other"} <= seen

    def test_the_round_topn_arm_is_exactly_the_seven_measured_series(self):
        """The rule CAL-P127 benches drops this arm. If its membership moves, the
        2.62 pp verdict is about a different set of rows and must be re-folded."""
        got = sorted(s for s in REAL_SERIES if classify(s) == "round|topn")
        assert got == ["KXPGAR1TOP10", "KXPGAR1TOP20", "KXPGAR1TOP5",
                       "KXPGAR2TOP10", "KXPGAR2TOP5", "KXPGAR3TOP10",
                       "KXPGAR3TOP5"]

    def test_tournament_scoped_top_n_stays_out_of_the_round_arm(self):
        """The control the rule depends on: KXPGATOP5/10/20 are the well-calibrated
        mass (2.62-3.47 pp) and dropping them would delete a third of the cell."""
        for s in ("KXPGATOP5", "KXPGATOP10", "KXPGATOP20", "KXPGATOP40",
                  "KXLIVTOP5", "KXLIVTOP10"):
            assert classify(s) == "tourney|topn", s


class TestItIsWiredAndStaysSQL:
    def test_the_dimension_is_registered(self):
        assert "golfround" in cce.DIMENSIONS
        expr, join, pre = cce.DIMENSIONS["golfround"]
        assert expr is cce.GOLFROUND_EXPR
        assert join == cce.SERIES_JOIN
        assert pre == ""

    def test_it_is_not_a_per_chunk_dimension(self):
        """SILENT: ``golfround`` reads one column of one row and needs no pre-pass.
        Registering it as per-chunk would make every fold pay the ladder sweep."""
        assert "golfround" not in cce.PER_CHUNK_DIMENSIONS

    def test_it_registers_no_new_join_and_therefore_cannot_shatter_a_chunk(self):
        """It reuses ``SERIES_JOIN``, which is a row-level lookup on
        ``futures_markets``. A dimension that aggregated across markets could
        disagree with itself at a chunk boundary; this one cannot."""
        assert cce.GOLFROUND_JOIN is cce.SERIES_JOIN
        assert "GROUP BY" not in cce.GOLFROUND_JOIN.upper()

    def test_it_rebinds_none_of_the_rails_own_dimensions(self):
        for name in ("none", "age", "series", "shape", "sumband", "cpdrift",
                     "price_moved", "market_type"):
            assert name in cce.DIMENSIONS

    def test_the_patterns_stay_inside_the_agreeing_subset(self):
        """POSIX ``~`` and Python ``re`` agree only on the simple subset. If a
        pattern grows alternation, a backreference or a lazy quantifier, these
        tests stop being evidence about the SQL and must be replaced by a
        server-side differential."""
        for pat in _patterns():
            for feature in ("|", "\\1", "*?", "+?", "(?<", "(?="):
                assert feature not in pat, f"{pat!r} left the agreeing subset"

    def test_there_are_exactly_three_patterns(self):
        assert len(_patterns()) == 3, _patterns()
