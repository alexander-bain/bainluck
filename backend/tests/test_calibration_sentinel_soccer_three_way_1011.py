"""#1011 — the calibration sentinel must still SEE a broken soccer curve.

Before this PR every events-table soccer cohort returned ``('soccer_2way',
1.0)`` from ``classify_coverage``: the historical two-way pairs (draw dropped at
ingest) were excluded from the curve, so any soccer miscalibration was known
work. Once the curve admits soccer graded three-way (matches since release
v4636 whose pair keeps the draw and which ended at full time), that shortcut
would mark a newly broken three-way cohort fully EXPLAINED and suppress it —
masking exactly the regression #1011 has to surface (Root, 2026-10-12 21:34Z).

The contract now:

* the events scan grades admitted soccer three-way under ``structure_class =
  'three_way'`` (home, away, draw from the pre-kickoff consensus pair), the same
  rows and grade as the curve;
* every OTHER soccer row is the historical exclusion, counted per outcome as
  ``soccer_2way_n`` and folded into the union, with the published view built
  from its complement;
* ``classify_coverage`` has no soccer special case — union + threshold decide.

Row-level proof against real Postgres lives in
``tests/integration/test_calibration_soccer_three_way_1011_pg.py``.
"""

from app.tasks.calibration_sentinel import (
    DISP_EXCLUSION_WORKING,
    DISP_REAL_BREAK,
    KNOWN_CLASS_KEYS,
    SENTINEL_MCE_THRESHOLD,
    _EVENTS_MINING_SQL,
    _MINING_SCAN_PARAMS,
    _PLAYBOOK_BRANCHES,
    _UNION_KEY,
    _cohort_views,
    _finalize_cohort,
    _fold_row_into_cohort,
    _new_cohort,
    build_issue_body,
    classify_coverage,
    passes_flag,
    raw_vs_published,
)
from app.utils.soccer_three_way import SOCCER_THREE_WAY_PARAMS

NOW = 1_800_000_000.0


def _events_row(structure, bucket, n, winners, sum_prob, excluded):
    """One events-scan row, shaped exactly as ``_EVENTS_MINING_SQL`` emits it."""
    return {
        "provenance": "events", "source": "odds_api", "category": "soccer",
        "series_family": "events_moneyline", "structure_class": structure,
        "bucket": bucket, "n": n, "winners": winners, "sum_prob": sum_prob,
        "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
        "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
        "soccer_2way_n": n if excluded else 0,
        "any_known_n": n if excluded else 0,
        "pub_n": 0 if excluded else n,
        "pub_winners": 0 if excluded else winners,
        "pub_sum_prob": 0.0 if excluded else sum_prob,
        "min_created_at": None,
    }


def _mine(rows):
    """Fold rows into every cohort view, as ``_run_calibration_sentinel`` does."""
    cohorts = {}
    for row in rows:
        for ck in _cohort_views(row):
            c = cohorts.get(ck)
            if c is None:
                c = cohorts[ck] = _new_cohort(ck, row)
            _fold_row_into_cohort(c, row)
    for c in cohorts.values():
        _finalize_cohort(c, NOW)
    return cohorts


def _verdict(c):
    explained_by, coverage = classify_coverage(
        c["overlap_fractions"], c["category"], c["provenance"]
    )
    disposition, _ = raw_vs_published(
        c["mce"], c.get("published_mce"), c.get("published_n", 0),
        SENTINEL_MCE_THRESHOLD,
    )
    return explained_by, coverage, disposition


def _files(c):
    """The live-run suppression rule (``_suppressed`` in the run), negated."""
    explained_by, _, disposition = _verdict(c)
    return not explained_by and disposition != DISP_EXCLUSION_WORKING


#: Historical two-way soccer: the old draw-omission shape — the pair sums to 1,
#: so a 0.55 home leg wins ~40% of the time. Large, and always miscalibrated.
HISTORICAL = [
    _events_row("binary", 5, 20000, 8000, 11000.0, excluded=True),
    _events_row("binary", 4, 20000, 6000, 9000.0, excluded=True),
]

#: A BROKEN three-way curve after the cutoff: legs priced ~0.55 winning 20%.
BROKEN_THREE_WAY = [_events_row("three_way", 5, 1500, 300, 825.0, excluded=False)]

#: A HEALTHY three-way curve: legs priced ~0.25 winning ~25%, ~0.45 winning ~45%.
HEALTHY_THREE_WAY = [
    _events_row("three_way", 2, 1000, 250, 250.0, excluded=False),
    _events_row("three_way", 4, 1000, 450, 450.0, excluded=False),
]

THREE_WAY_KEY = (("provenance", "events"), ("category", "soccer"), ("structure", "three_way"))
BINARY_KEY = (("provenance", "events"), ("category", "soccer"), ("structure", "binary"))


class TestNoStructuralShortcut:
    def test_an_events_soccer_cohort_with_no_excluded_rows_is_not_explained(self):
        # The shortcut returned ('soccer_2way', 1.0) here, with no rows at all.
        assert classify_coverage({}, "soccer", "events") == (None, 0.0)
        assert classify_coverage({}, "soccer_epl", "events") == (None, 0.0)
        assert classify_coverage(
            {"soccer_2way": 0.0, _UNION_KEY: 0.0}, "soccer", "events"
        ) == (None, 0.0)

    def test_historical_two_way_still_explains_through_the_union(self):
        assert classify_coverage(
            {"soccer_2way": 1.0, _UNION_KEY: 1.0}, "soccer", "events"
        ) == ("soccer_2way", 1.0)

    def test_soccer_2way_is_in_the_shared_vocabulary_with_a_branch(self):
        assert "soccer_2way" in KNOWN_CLASS_KEYS
        assert "soccer_2way" in _PLAYBOOK_BRANCHES


class TestABrokenThreeWayCurveIsReal:
    def test_post_cutoff_three_way_cohort_files_as_a_real_break(self):
        # THE REGRESSION GUARD Root asked for: a miscalibrated three-way soccer
        # cohort is flagged, unexplained, a real break, and would FILE.
        c = _mine(HISTORICAL + BROKEN_THREE_WAY)[THREE_WAY_KEY]
        assert c["total_n"] == 1500
        assert passes_flag(c["total_n"], c["mce"], c["is_new_format"])
        explained_by, coverage, disposition = _verdict(c)
        assert explained_by is None
        assert coverage == 0.0
        assert disposition == DISP_REAL_BREAK
        assert _files(c)

    def test_historical_two_way_cohort_keeps_its_explanation(self):
        c = _mine(HISTORICAL + BROKEN_THREE_WAY)[BINARY_KEY]
        assert passes_flag(c["total_n"], c["mce"], c["is_new_format"])
        explained_by, coverage, _ = _verdict(c)
        assert (explained_by, coverage) == ("soccer_2way", 1.0)
        assert not _files(c)

    def test_a_healthy_three_way_curve_is_not_flagged(self):
        c = _mine(HISTORICAL + HEALTHY_THREE_WAY)[THREE_WAY_KEY]
        assert not passes_flag(c["total_n"], c["mce"], c["is_new_format"])

    def test_the_all_soccer_cohort_publishes_only_the_three_way_rows(self):
        # The coarse events/soccer cohort is explained by the historical rows,
        # and its PUBLISHED view is exactly the admitted three-way rows — the
        # curve users see — so the broken curve also reads as a real break
        # there, not as the exclusion working.
        c = _mine(HISTORICAL + BROKEN_THREE_WAY)[
            (("provenance", "events"), ("category", "soccer"))
        ]
        assert c["published_n"] == 1500
        assert c["overlap_counts"]["soccer_2way"] == 40000
        _, _, disposition = _verdict(c)
        assert disposition == DISP_REAL_BREAK


class TestScanContract:
    def test_the_events_scan_binds_the_curves_contract(self):
        assert _MINING_SCAN_PARAMS["events"] is SOCCER_THREE_WAY_PARAMS
        assert _MINING_SCAN_PARAMS["futures"] == {}
        for name in SOCCER_THREE_WAY_PARAMS:
            assert f":{name}" in _EVENTS_MINING_SQL, name

    def test_the_events_scan_emits_the_counted_class_and_three_way_structure(self):
        for col in ("soccer_2way_n", "any_known_n", "pub_n", "structure_class"):
            assert col in _EVENTS_MINING_SQL, col
        assert "'three_way' AS structure_class" in _EVENTS_MINING_SQL
        assert "GROUP BY category, structure_class, bucket" in _EVENTS_MINING_SQL

    def test_a_futures_row_folds_soccer_2way_as_zero(self):
        ck = (("provenance", "futures"), ("category", "soccer"))
        c = _new_cohort(ck, {})
        row = _events_row("binary", 5, 10, 3, 5.0, excluded=False)
        row.pop("soccer_2way_n")
        _fold_row_into_cohort(c, row)
        assert c["overlap_counts"]["soccer_2way"] == 0


class TestRenderer:
    def test_body_prints_the_counted_share_not_a_structural_claim(self):
        c = _mine(HISTORICAL + BROKEN_THREE_WAY)[THREE_WAY_KEY]
        body = build_issue_body(c, explained_by=None, coverage=0.0)
        assert "structural" not in body
        assert "soccer_2way: 0.0% of outcomes" in body
