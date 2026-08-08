"""CAL-P013 (#1544) — the sentinel must be able to EXPLAIN what the curve excludes.

The defect: the Calibration Sentinel measures MCE on the RAW population by design
(so a break cannot hide behind the curve's own filters — correct), but its
EXPLANATION vocabulary was a strict SUBSET of the exclusions the curve ships. Any
cohort dropped by a class the sentinel could not name read as a fully unexplained
P1 break.

Measured 2026-08-08, KXNHLAST (n=5,467, MCE 26.9pp, filed as P1 #1140):

    bucket  avg_predicted  actual
    1-6        0.07-0.54   tracks predicted closely
    7          0.686       0.125
    8          0.740       0.154
    9          0.884       0.108
    10         0.947       0.158

Buckets 7-10 are a CLIFF, not a slope: actual goes flat at ~0.13 regardless of
price, which is the signature of a price carrying no information. Those rows are
already dropped from the published curve by the prop-threshold exclusion — the
sentinel simply could not say so.

These tests pin the property that prevents a recurrence: the sentinel's overlap
vocabulary must cover the curve's exclusions, and it must do so by REUSING the
curve's predicate rather than re-typing it.
"""

import importlib

from app.tasks.calibration_sentinel import (
    SENTINEL_COVERAGE_THRESHOLD,
    _fold_row_into_cohort,
    _new_cohort,
    classify_coverage,
)
from app.tasks.precompute_calibration import (
    KALSHI_HOCKEY_HONEST_BAND_MAX,
    KALSHI_PROP_THRESHOLD_DEGENERATE_BAND,
    KALSHI_PROP_THRESHOLD_NAME_RE,
)

# ``app.tasks.calibration_sentinel`` resolves to the registered Celery task, not
# the module, so module-level attributes (the rendered SQL) need an explicit
# import_module rather than attribute access on the package.
cs = importlib.import_module("app.tasks.calibration_sentinel")


class TestVocabularyCoversTheCurve:
    def test_prop_threshold_is_a_known_overlap_class(self):
        assert "kalshi_prop_threshold" in _new_cohort((), {})["overlap_counts"]

    def test_predicate_is_imported_not_retyped(self):
        """A second definition of 'excluded' is how these drift apart. The
        sentinel must CALL the curve's SQL builder, and must not contain a
        hand-typed copy of the regex or the bands."""
        src = open(cs.__file__).read()
        assert "kalshi_prop_threshold_exclude_sql(" in src
        assert KALSHI_PROP_THRESHOLD_NAME_RE not in src, "regex was re-typed"
        assert f">= {KALSHI_PROP_THRESHOLD_DEGENERATE_BAND}" not in src, "band re-typed"
        assert f">= {KALSHI_HOCKEY_HONEST_BAND_MAX}" not in src, "hockey band re-typed"

    def test_rendered_sql_carries_the_curve_band_and_regex(self):
        sql = cs._FUTURES_MINING_SQL
        assert "is_kalshi_prop_threshold" in sql
        assert KALSHI_PROP_THRESHOLD_NAME_RE in sql
        assert str(KALSHI_HOCKEY_HONEST_BAND_MAX) in sql
        assert "fm.source = 'kalshi'" in sql

    def test_events_branch_supplies_the_column_as_zero(self):
        """Both UNION arms must project the same columns, and events are not
        Kalshi futures."""
        assert "0 AS kalshi_prop_threshold_n" in cs._EVENTS_MINING_SQL


class TestFoldingAndClassification:
    def _row(self, n=100, prop=0, **kw):
        base = {
            "n": n,
            "winners": 0,
            "sum_prob": 0.0,
            "bucket": 5,
            "malformed_binary_n": 0,
            "esports_bundle_n": 0,
            "mex_norm_n": 0,
            "void_n": 0,
            "heuristic_n": 0,
            "kalshi_prop_threshold_n": prop,
            "min_created_at": None,
        }
        base.update(kw)
        return base

    def test_counter_accumulates(self):
        c = _new_cohort((("series", "KXNHLAST"),), {})
        _fold_row_into_cohort(c, self._row(prop=40))
        _fold_row_into_cohort(c, self._row(prop=35))
        assert c["overlap_counts"]["kalshi_prop_threshold"] == 75

    def test_a_prop_threshold_cohort_is_now_EXPLAINED(self):
        """The whole point: KXNHLAST-shaped cohorts stop reading as unexplained."""
        key, frac = classify_coverage(
            {"kalshi_prop_threshold": 0.62, "malformed_binary": 0.0},
            category="hockey",
            provenance="futures",
        )
        assert key == "kalshi_prop_threshold"
        assert frac >= SENTINEL_COVERAGE_THRESHOLD

    def test_below_threshold_still_unexplained(self):
        """Non-vacuity: a small overlap must NOT silence a real break. If this
        ever passes as explained, the sentinel has been taught to lie."""
        key, frac = classify_coverage(
            {"kalshi_prop_threshold": 0.05},
            category="hockey",
            provenance="futures",
        )
        assert key is None
        assert frac == 0.05

    def test_a_genuinely_new_break_is_untouched(self):
        """table_tennis multi_nonmex (47pp, coverage 0.0) must stay unexplained."""
        key, frac = classify_coverage({}, category="table_tennis", provenance="futures")
        assert key is None

    def test_does_not_hijack_the_structural_soccer_class(self):
        key, _ = classify_coverage(
            {"kalshi_prop_threshold": 0.99},
            category="soccer",
            provenance="events",
        )
        assert key == "soccer_2way"


class TestCurveIsUnchanged:
    def test_sentinel_change_does_not_touch_the_curve_predicate(self):
        """This queue changes what the SENTINEL can EXPLAIN, never what the curve
        EXCLUDES. The curve's builder must still produce its documented shape."""
        from app.tasks.precompute_calibration import kalshi_prop_threshold_exclude_sql

        sql = kalshi_prop_threshold_exclude_sql(
            source="s", name="n", category="c",
            calibration_probability="cp", opening_probability="op",
        )
        assert "s = 'kalshi'" in sql
        assert f">= {KALSHI_HOCKEY_HONEST_BAND_MAX}" in sql
        assert f">= {KALSHI_PROP_THRESHOLD_DEGENERATE_BAND}" in sql
