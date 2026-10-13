"""#1905 sub-defect 2 — a hard 40% coverage cliff with no margin band.

CAL-P064 (8dc504f6) fixed sub-defect 1: coverage is the exact scan union, with an
interval when the sample-estimated ``poly_placeholder`` cannot join it. Its #1896
test only clears because it ADDS a second class (union 0.406), and its AMBIGUOUS
path only fires when a sampled class widens the interval. Neither covers the
issue's own second guard: a cohort at exactly 39.6% with NO other class and NO
sampled class. Before this file that cohort had lower == upper == 0.396, missed
the ambiguous interval, and its body read "UNEXPLAINED ... candidate NEW break" —
word for word what it would say at 0%.

The threshold and the automatic decision are deliberately unchanged: the cohort
still files (a suppressed real break is the worse error). Only the diagnosis the
reader is handed changes.
"""

import app.tasks.bug_report_github as gh
import app.tasks.calibration_sentinel as cs
from app.tasks.calibration_sentinel import (
    COVERAGE_AMBIGUOUS,
    COVERAGE_EXPLAINED,
    COVERAGE_PARTIAL,
    COVERAGE_UNEXPLAINED,
    SENTINEL_COVERAGE_THRESHOLD,
    _UNION_KEY,
    _finalize_cohort,
    _new_cohort,
    build_issue_body,
    classify_coverage,
    coverage_band,
    coverage_bounds,
    file_cohort_issue,
)

UNEXPLAINED_HEADING = "UNEXPLAINED by any shipped exclusion"
PARTIAL_HEADING = "PARTIALLY EXPLAINED — verify the exclusion covers this cohort"


def _filed_body(overlap_counts: dict[str, int], n: int = 2000):
    """Fold a real cohort through the real classifier and renderer — no
    poly_placeholder is attached, so nothing is sample-estimated."""
    c = _new_cohort(
        (("category", "tennis"), ("provenance", "futures"), ("structure", "binary")), {}
    )
    c["buckets"][8] = {"bucket": 8, "n": n, "winners": int(n * 0.3), "sum_prob": n * 0.85}
    c["total_n"] = n
    c["overlap_counts"].update(overlap_counts)
    _finalize_cohort(c, now_ts=1_800_000_000.0)
    assert "poly_placeholder" not in c["overlap_fractions"]
    by, cov = classify_coverage(c["overlap_fractions"], c["category"], c["provenance"])
    return c, by, cov, build_issue_body(c, explained_by=by, coverage=cov)


class TestPure396Control:
    def test_threshold_is_unchanged(self):
        assert SENTINEL_COVERAGE_THRESHOLD == 0.40

    def test_exact_396_with_no_sampled_class_still_files(self):
        # THE SPECIMEN: #1896 tennis/binary, malformed_binary 39.6% alone.
        fracs = {"malformed_binary": 0.396, _UNION_KEY: 0.396}
        by, cov = classify_coverage(fracs, "tennis", "futures")
        assert by is None, "the lower-bound decision is unchanged — it still files"
        assert cov == 0.396
        assert coverage_bounds(fracs) == (0.396, 0.396), "a point, not an interval"

    def test_exact_396_is_partial_not_unexplained(self):
        assert coverage_band({"malformed_binary": 0.396, _UNION_KEY: 0.396}) == COVERAGE_PARTIAL

    def test_exact_396_body_says_partially_explained(self):
        c, by, cov, body = _filed_body({_UNION_KEY: 792, "malformed_binary": 792})
        assert by is None and cov == 0.396
        assert PARTIAL_HEADING in body
        assert UNEXPLAINED_HEADING not in body
        assert "candidate NEW break" not in body
        assert "AMBIGUOUS" not in body
        assert "39.6%" in body
        assert "**malformed_binary**" in body, "the reader is sent to the dominant exclusion"

    def test_zero_coverage_is_not_treated_the_same(self):
        # The other direction (gotcha #43): 0% keeps the NEW-break language.
        c, by, cov, body = _filed_body({})
        assert by is None and cov == 0.0
        assert coverage_band(c["overlap_fractions"]) == COVERAGE_UNEXPLAINED
        assert UNEXPLAINED_HEADING in body
        assert "candidate NEW break" in body
        assert PARTIAL_HEADING not in body


class TestPartialFilesThroughTheRealFilingPath:
    """Partial is NOT suppression: the run loop's ``_suppressed`` reads
    ``bool(explained_by)``, so a partial cohort must reach ``file_cohort_issue``
    with ``explained_by=None`` and be FILED, carrying the partial body."""

    def _file(self, monkeypatch, overlap_counts):
        c, by, cov, _ = _filed_body(overlap_counts)
        created = {}

        def fake_create(title, body, labels):
            created.update(title=title, body=body, labels=labels)
            return 4242, "NODE_4242"

        monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
        monkeypatch.setattr(gh, "create_github_issue", fake_create)
        monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
        monkeypatch.setattr(cs, "_find_open_issue_by_fingerprint", lambda fp: None)
        return by, file_cohort_issue(c, by, cov), created

    def test_exact_396_is_filed_with_the_partial_body(self, monkeypatch):
        by, res, created = self._file(monkeypatch, {_UNION_KEY: 792, "malformed_binary": 792})
        assert by is None, "explained_by must stay None or _suppressed() drops it"
        assert res["action"] == "filed"
        assert PARTIAL_HEADING in created["body"]
        assert "candidate NEW break" not in created["body"]
        assert any(lbl.startswith("priority:") for lbl in created["labels"])

    def test_zero_coverage_is_filed_as_a_new_break(self, monkeypatch):
        by, res, created = self._file(monkeypatch, {})
        assert res["action"] == "filed"
        assert "candidate NEW break" in created["body"]
        assert PARTIAL_HEADING not in created["body"]


class TestPartialNeverClaimsMeasuredCertaintyItLacks:
    def test_exact_union_reads_as_a_measured_point(self):
        _, _, _, body = _filed_body({_UNION_KEY: 792, "malformed_binary": 792})
        assert "cover **39.6%**" in body
        assert "lower bound" not in body

    def test_missing_union_reads_as_a_floor(self):
        # A scan row with no any_known_n folds the union as 0, so the largest
        # single class is a floor on the true union, not a count of it.
        _, _, _, body = _filed_body({"malformed_binary": 792})
        assert PARTIAL_HEADING in body
        assert "cover at least **39.6%**" in body
        assert "no exact union" in body

    def test_sampled_class_reads_as_a_floor(self):
        # A sampled class that can lift the union over the line is AMBIGUOUS;
        # a placeholder-only 38% (no counted union) is partial, but a floor.
        c, _, _, _ = _filed_body({_UNION_KEY: 700, "void": 700})
        c["overlap_fractions"]["poly_placeholder"] = 0.36
        assert coverage_bounds(c["overlap_fractions"])[1] >= SENTINEL_COVERAGE_THRESHOLD
        assert coverage_band(c["overlap_fractions"]) == COVERAGE_AMBIGUOUS
        c["overlap_fractions"]["poly_placeholder"] = 0.38
        c["overlap_fractions"][_UNION_KEY] = 0.0
        c["overlap_fractions"]["void"] = 0.0
        body = build_issue_body(c, explained_by=None, coverage=0.38)
        assert "cover at least **38.0%**" in body


class TestBandEdges:
    def test_band_floor_is_inclusive_at_exactly_35(self):
        c, by, cov, body = _filed_body({_UNION_KEY: 700, "void": 700})
        assert cov == 0.35
        assert coverage_band(c["overlap_fractions"]) == COVERAGE_PARTIAL
        assert PARTIAL_HEADING in body

    def test_just_below_the_band_is_unexplained(self):
        c, by, cov, body = _filed_body({_UNION_KEY: 698, "void": 698})
        assert cov == 0.349
        assert coverage_band(c["overlap_fractions"]) == COVERAGE_UNEXPLAINED
        assert UNEXPLAINED_HEADING in body

    def test_at_threshold_is_explained_and_suppressed(self):
        fracs = {"malformed_binary": 0.40, _UNION_KEY: 0.40}
        assert classify_coverage(fracs, "tennis", "futures")[0] == "malformed_binary"
        assert coverage_band(fracs) == COVERAGE_EXPLAINED


class TestIntervalSafeguardsPreserved:
    def test_ambiguous_still_wins_when_lower_is_in_the_band(self):
        # Lower 37% is inside the band, but the sampled class can lift the true
        # union over the line — that is AMBIGUOUS, the stronger statement.
        fracs = {"malformed_binary": 0.37, "poly_placeholder": 0.05, _UNION_KEY: 0.37}
        assert coverage_band(fracs) == COVERAGE_AMBIGUOUS

    def test_1895_shape_stays_ambiguous(self):
        fracs = {"malformed_binary": 0.302, "poly_placeholder": 0.140, _UNION_KEY: 0.302}
        assert coverage_band(fracs) == COVERAGE_AMBIGUOUS

    def test_sampled_class_is_never_summed_into_the_band(self):
        # 20% exact + 15% sampled: the upper bound is 35%, the lower 20%. Adding
        # them would invent a disjointness and land on the band floor; the lower
        # bound governs, so this stays UNEXPLAINED.
        fracs = {"void": 0.20, "poly_placeholder": 0.15, _UNION_KEY: 0.20}
        assert coverage_bounds(fracs) == (0.20, 0.35)
        assert coverage_band(fracs) == COVERAGE_UNEXPLAINED
