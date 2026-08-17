"""CAL-P064 — the four Calibration Sentinel instrument defects (#1903-#1906).

These are findings ABOUT THE DETECTOR, not about any cohort. CAL-P063 triaged the
2026-08-17 red list and found that four of its ten cells could not be read at face
value, because the instrument that produced them mis-classifies:

  #1903  _cohort_where silently drops the `series` and `structure` dims despite a
         docstring claiming it honours them, so the evidence pack on a
         series-keyed cell is drawn from the WHOLE source/category.
  #1904  the issue renderer walks a hard-coded tuple of six class names, so
         `kalshi_prop_threshold` is counted in the diagnosis and never printed.
  #1905  classify_coverage compares the MAX single class to the threshold rather
         than the union, so two shipped exclusions covering 30% + 14% score 0.30
         and the cohort files as a fully UNEXPLAINED P1.
  #1906  the capture axis has no n-floor and no season awareness (covered in
         tests/test_capture_census.py, where that logic lives).

Why these are fixed BEFORE any cell is chased: a detector that drops dimensions
hands you the wrong population, so fixing the instrument changes the red list
itself. Chasing cells first is chasing an artifact.

Every test here names the specimen it is anchored to, so a future reader can tell
a regression from a deliberate re-tune.
"""

from app.tasks.calibration_sentinel import (
    KNOWN_CLASS_KEYS,
    SENTINEL_COVERAGE_THRESHOLD,
    _UNION_KEY,
    _cohort_where,
    _finalize_cohort,
    _fold_row_into_cohort,
    _new_cohort,
    _PLAYBOOK_BRANCHES,
    _structure_predicate,
    build_issue_body,
    classify_coverage,
    coverage_bounds,
)


def _cohort(dims, buckets=None, overlap=None):
    ck = tuple(sorted(dims.items()))
    c = _new_cohort(ck, {})
    if buckets:
        for i, (n, w, sp) in enumerate(buckets):
            c["buckets"][i] = {"bucket": i, "n": n, "winners": w, "sum_prob": sp}
            c["total_n"] += n
    if overlap:
        c["overlap_counts"].update(overlap)
    return c


# ---------------------------------------------------------------------------
# #1903 — _cohort_where must honour `series`; `structure` must be expressible.
# ---------------------------------------------------------------------------
class TestCohortWhereHonoursItsDims:
    def test_series_dim_reaches_the_where_clause(self):
        # THE SPECIMEN: #1142 is titled `series=KXNHLGOAL` and every sample row
        # came back KXATPMATCH-* / KXMLBKS-*. The evidence attached to the red
        # cell was not evidence of the red cell.
        where, params = _cohort_where(
            {"provenance": "futures", "source": "kalshi", "series": "KXNHLGOAL"}
        )
        assert ":series" in where
        assert params["series"] == "KXNHLGOAL"
        assert "split_part" in where, "series must be derived the way the scan derives it"

    def test_series_matches_the_mining_scans_own_expression(self):
        # If these two ever diverge, the evidence pack silently samples a
        # DIFFERENT cohort than the census counted -- which is #1903 again with a
        # new cause. Pin the shape.
        from app.tasks.calibration_sentinel import _SERIES_FAMILY_SQL

        where, _ = _cohort_where({"source": "kalshi", "series": "KXNHLGOAL"})
        assert _SERIES_FAMILY_SQL in where
        assert "fm.source IN ('kalshi', 'datagolf')" in _SERIES_FAMILY_SQL

    def test_source_and_category_still_honoured(self):
        where, params = _cohort_where(
            {"provenance": "futures", "source": "polymarket", "category": "mma"}
        )
        assert params == {"src": "polymarket", "cat": "mma"}
        assert "fm.status = 'resolved'" in where

    def test_absent_dims_add_no_clause(self):
        where, params = _cohort_where({"provenance": "futures"})
        assert params == {}
        assert where == "fm.status = 'resolved'"

    def test_structure_predicate_mirrors_the_mining_case(self):
        # Same four branches, same order of precedence as _FUTURES_MINING_SQL.
        assert _structure_predicate({"structure": "binary"}) == "n_out = 2"
        assert _structure_predicate({"structure": "mex_multi"}) == "n_out >= 3 AND mutually_exclusive"
        assert "NOT COALESCE(mutually_exclusive, false)" in _structure_predicate(
            {"structure": "multi_nonmex"}
        )
        assert _structure_predicate({"structure": "single"}) == "n_out <= 1"

    def test_structure_predicate_is_none_when_unkeyed(self):
        # A cohort with no structure dim must not acquire a filter.
        assert _structure_predicate({"provenance": "futures"}) is None
        assert _structure_predicate({"structure": "not_a_class"}) is None

    def test_structure_is_not_in_the_where_clause(self):
        # Deliberate: a correlated per-market COUNT in the WHERE would run over
        # the whole category BEFORE the caller's :cap could bound it, which is the
        # runaway shape the caps exist to prevent. It belongs after the cap.
        where, params = _cohort_where({"source": "kalshi", "structure": "binary"})
        assert "n_out" not in where
        assert "structure" not in params


# ---------------------------------------------------------------------------
# #1905 — coverage is the UNION, not the max single class.
# ---------------------------------------------------------------------------
class TestCoverageUsesTheUnion:
    def test_scan_counted_classes_union_to_clear_the_threshold(self):
        # Two SCAN-COUNTED classes: the union is exact, so the decision is exact.
        by, cov = classify_coverage(
            {"malformed_binary": 0.30, "void": 0.14, _UNION_KEY: 0.42}, "tech", "futures"
        )
        assert cov >= SENTINEL_COVERAGE_THRESHOLD
        assert by == "malformed_binary", "the DOMINANT class still names the playbook branch"

    def test_sample_estimated_placeholder_cannot_be_added_silently(self):
        # THE SPECIMEN: #1895 poly/mma -- malformed_binary 30.2% (exact) +
        # poly_placeholder 14.0% (SAMPLE-estimated). The true union is somewhere
        # in [30.2%, 44.2%] and the 40% threshold is INSIDE that interval.
        #
        # The automatic decision must take the LOWER bound and keep filing: a
        # suppressed real break ships miscalibration to users, while an
        # over-filed cell only makes noise. Adding the two to reach 44.2% would
        # be inventing a disjointness we have not measured.
        fracs = {"malformed_binary": 0.302, "poly_placeholder": 0.140, _UNION_KEY: 0.302}
        by, cov = classify_coverage(fracs, "mma", "futures")
        assert by is None, "must still file — the lower bound governs"
        assert cov == 0.302
        lower, upper = coverage_bounds(fracs)
        assert (lower, round(upper, 3)) == (0.302, 0.442)
        assert lower < SENTINEL_COVERAGE_THRESHOLD <= upper, "the threshold is inside the interval"

    def test_the_0_4pp_miss_that_filed_1896(self):
        # THE SPECIMEN: #1896 was filed UNEXPLAINED because malformed_binary
        # measured 39.6% against a 40.0% threshold. With any other known class
        # present at all, the union clears.
        fracs = {"malformed_binary": 0.396, "void": 0.02, _UNION_KEY: 0.406}
        assert classify_coverage(fracs, "tennis", "futures")[0] is not None

    def test_exact_union_is_preferred_over_the_sum(self):
        # The classes are NOT disjoint, so summing overstates. When the exact
        # SQL-counted union says 45%, that is the number -- not 30+25=55%.
        by, cov = classify_coverage(
            {"malformed_binary": 0.30, "void": 0.25, _UNION_KEY: 0.45}, "tech", "futures"
        )
        assert cov == 0.45
        assert by == "malformed_binary"

    def test_union_key_never_names_a_class(self):
        # It is a number, not a diagnosis: it must never be returned as
        # `explained_by`, because there is no playbook branch for it.
        by, cov = classify_coverage({_UNION_KEY: 0.99}, "tech", "futures")
        assert by is None
        assert cov == 0.99

    def test_genuinely_uncovered_cohort_still_files(self):
        # The other direction (gotcha #43). Raising coverage must not silence a
        # real break -- a union of 12% is still UNEXPLAINED.
        by, cov = classify_coverage(
            {"malformed_binary": 0.08, "void": 0.04, _UNION_KEY: 0.12}, "tech", "futures"
        )
        assert by is None
        assert cov < SENTINEL_COVERAGE_THRESHOLD

    def test_falls_back_to_max_when_union_absent(self):
        # Older cached findings have no union key. They must keep their previous
        # behaviour rather than reading 0% coverage and re-filing everything.
        by, cov = classify_coverage({"poly_placeholder": 0.6}, "economics", "futures")
        assert by == "poly_placeholder"
        assert cov == 0.6

    def test_soccer_events_shortcut_is_unchanged(self):
        assert classify_coverage({}, "soccer_epl", "events") == ("soccer_2way", 1.0)

    def test_union_folds_additively_across_scan_rows(self):
        # The mining scan groups by (source, category, series, structure, bucket),
        # so no OUTCOME appears in two rows and the per-row unions sum to the
        # cohort union. Guards the fold, not just the SQL.
        c = _cohort({"provenance": "futures", "category": "tennis"})
        for _ in range(3):
            _fold_row_into_cohort(c, {
                "bucket": 5, "n": 100, "winners": 30, "sum_prob": 50.0,
                "malformed_binary_n": 20, "esports_bundle_n": 0, "mex_norm_n": 0,
                "void_n": 10, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
                "any_known_n": 25,   # union < 20+10: the two classes overlap
            })
        assert c["overlap_counts"][_UNION_KEY] == 75
        _finalize_cohort(c, now_ts=1_800_000_000.0)
        assert c["overlap_fractions"][_UNION_KEY] == 0.25

    def test_missing_any_known_n_does_not_crash_the_fold(self):
        # A cached/older scan row without the new column must fold to 0, not raise.
        c = _cohort({"provenance": "futures", "category": "tennis"})
        _fold_row_into_cohort(c, {
            "bucket": 5, "n": 10, "winners": 3, "sum_prob": 5.0,
            "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
            "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
        })
        assert c["overlap_counts"][_UNION_KEY] == 0


# ---------------------------------------------------------------------------
# #1904 — the renderer must print the whole vocabulary it diagnoses on.
# ---------------------------------------------------------------------------
class TestRendererPrintsEveryKnownClass:
    def _body(self, overlap, **kw):
        buckets = [(0, 0, 0.0)] * 10
        buckets[8] = (2000, 600, 1700.0)
        c = _cohort(
            {"provenance": "futures", "source": "kalshi", "series": "KXNHLGOAL"},
            buckets=buckets,
            overlap=overlap,
        )
        _finalize_cohort(c, now_ts=1_800_000_000.0)
        return c, build_issue_body(c, **kw)

    def test_kalshi_prop_threshold_is_printed(self):
        # THE SPECIMEN: #1142 and #1143 are 100% ladder-named prop thresholds and
        # NEITHER issue body contained the words. The single class that explains
        # the cell was the one the reader could not see.
        _, body = self._body(
            {"kalshi_prop_threshold": 2000}, explained_by=None, coverage=0.1
        )
        assert "kalshi_prop_threshold" in body

    def test_renderer_covers_the_shared_vocabulary_exactly(self):
        # The regression guard for the CLASS of bug, not the instance: every key
        # the diagnosis can count must be renderable. A new class added to
        # KNOWN_CLASS_KEYS without a render path fails here.
        overlap = {k: 100 for k in KNOWN_CLASS_KEYS if k != "poly_placeholder"}
        _, body = self._body(overlap, explained_by=None, coverage=0.1)
        for key in overlap:
            assert key in body, f"{key} counted in the diagnosis but never printed"

    def test_union_line_names_the_thresholded_number(self):
        # A reader given only per-class rows can reconstruct a MAX and reach a
        # different verdict than the sentinel did. Print what was compared.
        _, body = self._body(
            {"malformed_binary": 800, _UNION_KEY: 900}, explained_by=None, coverage=0.45
        )
        assert "union of the above" in body
        assert "coverage threshold" in body

    def test_every_known_class_has_a_playbook_branch(self):
        # #1904's second half: `kalshi_prop_threshold` was counted AND had no
        # branch, so even once printed the reader was sent to the playbook index
        # instead of to the exclusion that already handles the cell.
        for key in KNOWN_CLASS_KEYS:
            assert key in _PLAYBOOK_BRANCHES, f"{key} has no playbook branch"

    def test_prop_threshold_branch_warns_about_raw_vs_published(self):
        # The actionable half of #1142: raw 21.33pp vs published 3.69pp. Whoever
        # reads the cell must be told to compare against the PUBLISHED curve
        # before treating it as a break.
        _, body = self._body(
            {"kalshi_prop_threshold": 2000},
            explained_by="kalshi_prop_threshold",
            coverage=0.95,
        )
        assert "published" in body.lower()
        assert "CAL-P013" in body


class TestAmbiguousCoverageIsSaidOutLoud:
    """#1905's other half: when the threshold falls inside the coverage
    interval, the body must not claim the cell is a NEW break."""

    def _body(self, overlap_counts, total_n_bucket):
        buckets = [(0, 0, 0.0)] * 10
        buckets[8] = total_n_bucket
        c = _cohort(
            {"provenance": "futures", "source": "polymarket", "category": "mma"},
            buckets=buckets,
            overlap=overlap_counts,
        )
        _finalize_cohort(c, now_ts=1_800_000_000.0)
        # poly_placeholder arrives post-hoc from the snapshot sample, not the scan.
        c["overlap_fractions"]["poly_placeholder"] = 0.140
        by, cov = classify_coverage(c["overlap_fractions"], c["category"], c["provenance"])
        return by, cov, build_issue_body(c, explained_by=by, coverage=cov)

    def test_straddling_cohort_renders_ambiguous_not_unexplained(self):
        by, cov, body = self._body({_UNION_KEY: 604, "malformed_binary": 604}, (2000, 600, 1700.0))
        assert by is None
        assert "AMBIGUOUS" in body
        assert "UNEXPLAINED by any shipped exclusion" not in body
        assert "30.2%" in body and "44.2%" in body

    def test_genuinely_new_break_still_says_unexplained(self):
        # The other direction: a cohort with almost no known-class coverage must
        # keep the plain NEW-break language and the row-trace instruction.
        buckets = [(0, 0, 0.0)] * 10
        buckets[8] = (2000, 600, 1700.0)
        c = _cohort(
            {"provenance": "futures", "source": "kalshi", "category": "tech"},
            buckets=buckets,
            overlap={_UNION_KEY: 40, "void": 40},
        )
        _finalize_cohort(c, now_ts=1_800_000_000.0)
        body = build_issue_body(c, explained_by=None, coverage=0.02)
        assert "UNEXPLAINED by any shipped exclusion" in body
        assert "AMBIGUOUS" not in body
        assert "row-trace protocol" in body
