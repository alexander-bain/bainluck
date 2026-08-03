"""Unit tests for the Calibration Sentinel (#1054) pure logic.

These cover the detection/classification math and the evidence-pack rendering —
the parts that decide whether a cohort is flagged, whether it maps to a known
class, and what the filed issue says. The DB scan + httpx filing are exercised
via the admin inline endpoint / live run, not here.
"""

from app.tasks.calibration_sentinel import (
    SENTINEL_COVERAGE_THRESHOLD,
    build_issue_body,
    build_issue_title,
    classify_coverage,
    cohort_fingerprint,
    hook_signature,
    passes_flag,
    series_family,
    severity_for,
    structure_class,
)
from app.tasks.calibration_sentinel import (
    _empty_buckets,
    _finalize_cohort,
    _new_cohort,
    dedup_overlapping,
)


def _mk(dims, mce):
    ck = tuple(sorted(dims.items()))
    c = _new_cohort(ck, {})
    c["mce"] = mce
    return c


class TestDedupOverlapping:
    def test_nested_views_of_same_break_collapse(self):
        # highest-severity, most-specific survives; coarser/finer cuts drop
        cohorts = [
            _mk({"provenance": "futures", "source": "polymarket", "category": "hockey"}, 16.4),
            _mk({"provenance": "futures", "category": "hockey"}, 12.0),
            _mk({"provenance": "futures", "source": "polymarket", "series": "hockey"}, 16.4),
        ]
        kept = dedup_overlapping(cohorts)
        assert len(kept) == 1
        assert kept[0]["dims"]["source"] == "polymarket"

    def test_disjoint_breaks_both_survive(self):
        cohorts = [
            _mk({"provenance": "futures", "source": "polymarket", "category": "hockey"}, 16.4),
            _mk({"provenance": "futures", "source": "polymarket", "category": "tennis"}, 13.0),
        ]
        assert len(dedup_overlapping(cohorts)) == 2


def _cohort(dims, buckets=None, overlap=None, min_created=None):
    ck = tuple(sorted(dims.items()))
    c = _new_cohort(ck, {})
    if buckets:
        for i, (n, w, sp) in enumerate(buckets):
            c["buckets"][i] = {"bucket": i, "n": n, "winners": w, "sum_prob": sp}
            c["total_n"] += n
    if overlap:
        c["overlap_counts"].update(overlap)
    c["min_created_at"] = min_created
    return c


class TestSeriesFamily:
    def test_kalshi_ticker_prefix(self):
        assert series_family("KXPGATOUR-THOC26") == "KXPGATOUR"

    def test_strips_trailing_digits(self):
        # season suffixes fold together
        assert series_family("KXNBA2026") == "KXNBA"
        assert series_family("KXNBA2025") == "KXNBA"

    def test_none(self):
        assert series_family(None) == "unknown"


class TestStructureClass:
    def test_binary(self):
        assert structure_class(2, True) == "binary"

    def test_mex_multi(self):
        assert structure_class(8, True) == "mex_multi"

    def test_multi_nonmex(self):
        assert structure_class(8, False) == "multi_nonmex"

    def test_single(self):
        assert structure_class(1, True) == "single"


class TestFlagRule:
    def test_established_needs_floor_and_threshold(self):
        assert passes_flag(2000, 6.0, is_new_format=False) is True
        assert passes_flag(500, 6.0, is_new_format=False) is False   # under n floor
        assert passes_flag(2000, 4.0, is_new_format=False) is False  # under mce threshold

    def test_new_format_is_looser(self):
        # would NOT flag as established, DOES flag as new-format
        assert passes_flag(400, 3.5, is_new_format=False) is False
        assert passes_flag(400, 3.5, is_new_format=True) is True

    def test_none_mce(self):
        assert passes_flag(9999, None, is_new_format=True) is False


class TestSeverity:
    def test_big_established_is_p1(self):
        assert severity_for(12.0, False) == "P1"

    def test_moderate_is_p2(self):
        assert severity_for(6.0, False) == "P2"

    def test_new_format_is_p3(self):
        assert severity_for(12.0, True) == "P3"


class TestHookSignature:
    def test_high_cp_underperforming_is_hook(self):
        # top band predicts ~0.9 but resolves ~0.3 → the sign/placeholder hook
        buckets = _empty_buckets()
        buckets[8] = {"bucket": 8, "n": 100, "winners": 30, "sum_prob": 85.0}
        buckets[9] = {"bucket": 9, "n": 100, "winners": 25, "sum_prob": 95.0}
        assert hook_signature(buckets) is True

    def test_calibrated_high_band_is_not_hook(self):
        buckets = _empty_buckets()
        buckets[8] = {"bucket": 8, "n": 100, "winners": 84, "sum_prob": 85.0}
        buckets[9] = {"bucket": 9, "n": 100, "winners": 93, "sum_prob": 95.0}
        assert hook_signature(buckets) is False

    def test_small_top_band_ignored(self):
        buckets = _empty_buckets()
        buckets[9] = {"bucket": 9, "n": 10, "winners": 0, "sum_prob": 9.5}
        assert hook_signature(buckets) is False


class TestClassifyCoverage:
    def test_soccer_events_is_structural_draw_class(self):
        by, cov = classify_coverage({}, "soccer_epl", "events")
        assert by == "soccer_2way"
        assert cov == 1.0

    def test_esports_bundle_majority_explains(self):
        by, cov = classify_coverage(
            {"esports_multi_bundle": 0.8, "void": 0.1}, "esports", "futures"
        )
        assert by == "esports_multi_bundle"
        assert cov >= SENTINEL_COVERAGE_THRESHOLD

    def test_placeholder_explains(self):
        by, cov = classify_coverage({"poly_placeholder": 0.6}, "economics", "futures")
        assert by == "poly_placeholder"

    def test_below_threshold_is_unexplained(self):
        by, cov = classify_coverage(
            {"void": 0.1, "heuristic": 0.2}, "tech", "futures"
        )
        assert by is None
        assert cov < SENTINEL_COVERAGE_THRESHOLD


class TestFingerprintStability:
    def test_order_independent(self):
        a = cohort_fingerprint((("source", "kalshi"), ("category", "golf")))
        b = cohort_fingerprint((("category", "golf"), ("source", "kalshi")))
        assert a == b

    def test_distinct_cohorts_differ(self):
        a = cohort_fingerprint((("source", "kalshi"),))
        b = cohort_fingerprint((("source", "polymarket"),))
        assert a != b


class TestFinalizeAndRediscovery:
    """The acceptance-shaped tests: a cohort carrying a known-class signature
    finalizes to a flag + the right classification (the rediscovery contract)."""

    def test_mex_normalization_cohort_flags_and_classifies(self):
        # a mex >=3 cohort over-predicting hard, with the mex_norm overlap
        buckets = [(0, 0, 0.0)] * 10
        buckets[7] = (2000, 600, 1500.0)  # predicts .75 resolves .30
        buckets[8] = (1500, 300, 1275.0)
        c = _cohort(
            {"provenance": "futures", "category": "football", "structure": "mex_multi"},
            buckets=buckets,
            overlap={"mex_normalization": 3200},
        )
        _finalize_cohort(c, now_ts=1_800_000_000.0)
        assert passes_flag(c["total_n"], c["mce"], c["is_new_format"]) is True
        by, cov = classify_coverage(c["overlap_fractions"], c["category"], c["provenance"])
        assert by == "mex_normalization"

    def test_new_format_detection_from_recent_created_at(self):
        buckets = [(0, 0, 0.0)] * 10
        buckets[8] = (400, 120, 340.0)
        c = _cohort(
            {"provenance": "futures", "source": "kalshi", "series": "KXOLY"},
            buckets=buckets,
        )
        import time as _t
        c["min_created_at"] = _DummyDT(_t.time() - 5 * 86400)  # 5 days old
        _finalize_cohort(c, now_ts=_t.time())
        assert c["is_new_format"] is True

    def test_unexplained_cohort_renders_new_break_body(self):
        buckets = [(0, 0, 0.0)] * 10
        buckets[8] = (2000, 600, 1700.0)
        c = _cohort(
            {"provenance": "futures", "category": "tech", "source": "kalshi"},
            buckets=buckets,
        )
        _finalize_cohort(c, now_ts=1_800_000_000.0)
        title = build_issue_title(c)
        body = build_issue_body(c, explained_by=None, coverage=0.1)
        assert "Calibration Sentinel" in title
        assert f"sentinel-fingerprint:{c['fingerprint']}" in body
        assert "UNEXPLAINED" in body
        assert "Per-bucket census" in body


class _DummyDT:
    """Minimal stand-in with a .timestamp() for _finalize_cohort's age math."""

    def __init__(self, ts):
        self._ts = ts

    def timestamp(self):
        return self._ts


# ---------------------------------------------------------------------------
# Capture-mass / pass-rate cohort axis (2026-08-03 addendum) — pure helpers.
# ---------------------------------------------------------------------------
from app.tasks.calibration_sentinel import (  # noqa: E402
    _capture_fingerprint,
    build_capture_issue_body,
    build_capture_issue_title,
)
from app.utils.capture_census import CaptureFinding  # noqa: E402


class TestCaptureAxis:
    def _finding(self):
        return CaptureFinding(
            kind="starved_class",
            cohort="baseball_mlb/moneyline",
            detail="147 moneyline markets across 231 games = 0.64/game.",
        )

    def test_capture_fingerprint_is_stable_and_prefixed(self):
        f = self._finding()
        fp1 = _capture_fingerprint(f)
        fp2 = _capture_fingerprint(self._finding())
        assert fp1 == fp2  # deterministic
        assert fp1.startswith("cap-") and len(fp1) == 16

    def test_capture_fingerprint_distinguishes_cohorts(self):
        a = _capture_fingerprint(self._finding())
        b = _capture_fingerprint(
            CaptureFinding(kind="starved_class", cohort="basketball_nba/moneyline",
                           detail="x")
        )
        assert a != b

    def test_capture_body_carries_dedup_marker(self):
        f = self._finding()
        fp = _capture_fingerprint(f)
        body = build_capture_issue_body(f, fp)
        # Reuses the SAME marker as MCE cohorts so the shared dedup search finds it.
        assert f"sentinel-fingerprint:{fp}" in body
        assert "capture-mass finding" in body
        assert f.detail in body

    def test_capture_title_names_kind_and_cohort(self):
        title = build_capture_issue_title(self._finding())
        assert "capture:" in title
        assert "baseball_mlb/moneyline" in title
        assert len(title) <= 256
