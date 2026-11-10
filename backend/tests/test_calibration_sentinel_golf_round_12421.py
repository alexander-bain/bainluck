"""#12421 / #12426: the sentinel can name the golf-round gate the curve already applies.

THE FILING. The Calibration Sentinel filed #12421 (``series=KXPGAR2TOP``, MCE
29.2pp, n=1516) and #12426 (``series=KXPGAR3TOP``, 20.8pp, n=1601) as P1 breaks
"UNEXPLAINED by any shipped exclusion", with the published MCE UNKNOWN.

THE READ (Builder E, Nov 9). Every one of those rows is already off the published
curve. ``golf_round_price_unanchored`` (#938, ``adfc7ec2d5``) withholds every
Kalshi golf market whose ticker's first segment names a round
(``R{n}LEAD`` / ``R{n}TOP{n}``): Kalshi gives such a market only the round's
close as its start time, so no stored price can be placed before the round. All
56 resolved markets in the two series are category golf and match. The served
``/api/calibration`` (generated 2026-11-10 01:47Z) reported
``golf_round_timing_filter.excluded = 19,066`` outcomes in 227 markets. The 231
losing legs priced at 90% or more that drive the "hook" are empty-book asks
promoted by the pre-#6126 candle rule, plus a few real 0.99 trades.

The sentinel scans raw rows on purpose. Its explanation vocabulary must still
cover what the curve excludes, or it files a P1 against a cohort that is already
handled (CAL-P013, the same class as #1140). These tests pin the class into that
vocabulary, keyed on the same structure the curve keys on, with the curve itself
untouched.
"""

import importlib
import re

from app.tasks.calibration_sentinel import (
    KNOWN_CLASS_KEYS,
    SENTINEL_COVERAGE_THRESHOLD,
    _fold_row_into_cohort,
    _new_cohort,
    classify_coverage,
)
from app.tasks.repair_golf_round_closing_line import ROUND_SERIES_PATTERN

# The package attribute is the Celery task; the module carries the rendered SQL.
cs = importlib.import_module("app.tasks.calibration_sentinel")
curve = importlib.import_module("app.tasks.precompute_calibration")

CLASS = "golf_round_price_unanchored"


class TestTheVocabularyCoversTheGolfRoundGate:
    def test_it_is_a_known_class(self):
        assert CLASS in KNOWN_CLASS_KEYS
        assert CLASS in _new_cohort((), {})["overlap_counts"]

    def test_the_scan_marks_and_counts_it(self):
        sql = cs._FUTURES_MINING_SQL
        assert "AS is_golf_round_price_unanchored" in sql
        assert "AS golf_round_price_unanchored_n" in sql

    def test_the_scan_keys_on_the_curves_structure(self):
        sql = cs._FUTURES_MINING_SQL
        assert f"~ '{ROUND_SERIES_PATTERN}'" in sql
        assert "fm.source = 'kalshi'" in sql
        assert "COALESCE(fm.llm_sport_category, 'unknown') = 'golf'" in sql

    def test_the_curve_withholds_on_the_same_pattern(self):
        # The sentinel imports the repair rail's constant; the curve writes the
        # literal (its fingerprint must cover it). Pin the two equal from here.
        src = open(curve.__file__).read()
        assert f"~ '{ROUND_SERIES_PATTERN}'" in src
        assert "golf_round_price_unanchored" in src

    def test_it_is_inside_the_known_union_so_survivors_exclude_it(self):
        # The union is interpolated once to count excluded rows and three
        # times to build the survivor aggregate from its complement.
        assert cs._FUTURES_MINING_SQL.count("OR is_golf_round_price_unanchored") == 4

    def test_the_events_scan_supplies_the_column_as_zero(self):
        assert "0 AS golf_round_price_unanchored_n" in cs._EVENTS_MINING_SQL

    def test_the_issue_body_has_a_playbook_line_for_it(self):
        assert CLASS in cs._PLAYBOOK_BRANCHES
        assert "#938" in cs._PLAYBOOK_BRANCHES[CLASS]


class TestThePatternIsTheRoundNotGolf:
    def test_the_filed_series_match(self):
        for series in ("KXPGAR2TOP10", "KXPGAR3TOP5", "KXPGAR1LEAD", "KXDPWORLDTOURR1LEAD"):
            assert re.search(ROUND_SERIES_PATTERN, series), series

    def test_tournament_long_golf_does_not(self):
        # The curve keeps these, so the sentinel must not explain them away.
        for series in ("KXPGATOP10", "KXPGATOUR", "KXPGATOURWINNER"):
            assert not re.search(ROUND_SERIES_PATTERN, series), series


class TestFoldingAndClassification:
    def _row(self, n, golf_round, **kw):
        row = {
            "n": n, "winners": 0, "sum_prob": 0.0, "bucket": 9,
            "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
            "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
            "golf_round_price_unanchored_n": golf_round,
            "any_known_n": golf_round,
            "pub_n": n - golf_round, "pub_winners": 0, "pub_sum_prob": 0.0,
            "min_created_at": None,
        }
        row.update(kw)
        return row

    def test_the_counter_accumulates(self):
        c = _new_cohort((("series", "KXPGAR2TOP"),), {})
        _fold_row_into_cohort(c, self._row(274, 274))
        _fold_row_into_cohort(c, self._row(324, 324))
        assert c["overlap_counts"][CLASS] == 598

    def test_a_row_from_an_older_scan_folds_as_zero(self):
        c = _new_cohort((("series", "KXNHLAST"),), {})
        row = self._row(10, 0)
        del row["golf_round_price_unanchored_n"]
        _fold_row_into_cohort(c, row)
        assert c["overlap_counts"][CLASS] == 0

    def test_the_12421_cohort_is_explained(self):
        # Every one of the 1,516 outcomes is in a round market.
        key, frac = classify_coverage(
            {CLASS: 1.0, "__any_known__": 1.0}, category="golf", provenance="futures"
        )
        assert key == CLASS
        assert frac >= SENTINEL_COVERAGE_THRESHOLD

    def test_a_small_overlap_still_files(self):
        # Non-vacuity: a cohort mostly OUTSIDE round markets is still a break.
        key, frac = classify_coverage(
            {CLASS: 0.05, "__any_known__": 0.05}, category="golf", provenance="futures"
        )
        assert key is None
        assert frac == 0.05
