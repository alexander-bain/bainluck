"""#1911 parity — a mining-mask complement is never called the published curve.

PILLAR: TRUTH. SHIP: Accuracy alerts stop saying excluded raw forecasts are
visible on the published chart; genuine raw-capture alarms remain visible.

Root's specimen (2026-10-15, `artifacts/calibration-10516-driver-20261015/
canonical-offline-packet/`): the canonical Weather trace rejects outcomes
218261839 and 222390511 at `is_below_writer_bar` — each the one priced losing
leg of a closed question. The immutable sentinel mining SQL, run over those two
rosters, counts both as raw AND as "published" (raw_n = pub_n = 1): its
complement only knows six exclusion classes, and the writer bar is not one. The
filed body then printed them under "PUBLISHED (what users see)".

What must hold:
  * futures cohorts report the published pair as UNKNOWN (None, None) and the
    scan's survivors under a label that says they are NOT the published curve;
  * a mask can neither suppress (`exclusion_working`) nor confirm
    (`real_break` / `exclusion_harms`) an alarm, so the raw alarm files;
  * a genuinely canonical comparison (events) keeps all four dispositions;
  * the selection-bias check (CAL-P067) still outranks everything.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_sentinel import (
    DISP_EXCLUSION_WORKING,
    DISP_NOT_PROVABLE,
    DISP_PUBLISHED_UNKNOWN,
    PUBLISHED_BASIS_CANONICAL,
    PUBLISHED_BASIS_LIMITED_MASK,
    _FUTURES_MINING_SQL,
    _finalize_cohort,
    _fold_row_into_cohort,
    _new_cohort,
    build_issue_body,
    build_reobservation_comment,
    published_basis,
    raw_vs_published,
)

THRESHOLD = 5.0


def _weather_row(bucket, n, winners, sum_prob):
    """A Kalshi weather scan row whose priced legs survive the six-class mask."""
    return {
        "source": "kalshi", "category": "weather", "series_family": "KXHIGHNY",
        "structure_class": "multi_nonmex", "provenance": "futures",
        "bucket": bucket, "n": n, "winners": winners, "sum_prob": sum_prob,
        "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
        "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
        "any_known_n": 0, "pub_n": n, "pub_winners": winners, "pub_sum_prob": sum_prob,
        "min_created_at": None,
    }


def _cohort(rows, provenance="futures"):
    key = (("provenance", provenance), ("source", "kalshi"), ("category", "weather"))
    c = _new_cohort(key, rows[0])
    for r in rows:
        _fold_row_into_cohort(c, r)
    c = _finalize_cohort(c, now_ts=0.0)
    c.update({
        "fingerprint": "f1911", "is_new_format": False, "hook_signature": False,
        "overlap_fractions": {}, "disposition": DISP_PUBLISHED_UNKNOWN,
        "disposition_why": "w",
    })
    return c


class TestRootsWeatherSpecimen:
    def test_the_writer_bar_rows_are_not_reported_as_published(self):
        # One priced losing leg each, as Root's projected rosters carry them.
        c = _cohort([_weather_row(2, 1, 0, 0.25), _weather_row(3, 1, 0, 0.35)])
        assert c["total_n"] == 2
        assert c["published_basis"] == PUBLISHED_BASIS_LIMITED_MASK
        assert c["published_mce"] is None and c["published_n"] is None
        assert c["mask_survivor_n"] == 2

    def test_the_body_says_unknown_and_names_the_mask(self):
        body = build_issue_body(
            _cohort([_weather_row(2, 300, 10, 75.0)]), None, 0.0
        )
        assert "PUBLISHED — what users see):** UNKNOWN" in body
        assert "Limited-mask survivors" in body and "NOT the published curve" in body
        assert "surviving the shipped exclusions" not in body

    def test_the_recurrence_says_unknown_and_names_the_mask(self):
        comment = build_reobservation_comment(_cohort([_weather_row(2, 300, 10, 75.0)]))
        assert "**PUBLISHED (what users see):** UNKNOWN" in comment
        assert "Limited-mask survivors" in comment
        assert "surviving the shipped exclusions" not in comment

    def test_a_cohort_that_does_not_name_its_basis_is_not_published(self):
        c = _cohort([_weather_row(2, 300, 10, 75.0)])
        c.pop("published_basis")
        c["published_mce"], c["published_n"] = 3.0, 300  # a stale, unlabelled pair
        assert "UNKNOWN" in build_reobservation_comment(c)


class TestAMaskDecidesNothing:
    @pytest.mark.parametrize("raw", [0.5, 4.9, 5.0, 21.33])
    @pytest.mark.parametrize("mask", [None, 0.1, 3.69, 7.57, 30.0])
    def test_a_limited_mask_only_ever_reads_unknown(self, raw, mask):
        disp, why = raw_vs_published(
            raw, None, 0, THRESHOLD,
            basis=PUBLISHED_BASIS_LIMITED_MASK, mask_mce=mask, mask_n=500,
        )
        assert disp == DISP_PUBLISHED_UNKNOWN
        assert f"raw {raw:.2f}pp" in why

    def test_even_a_published_number_passed_beside_a_mask_basis_is_ignored(self):
        disp, _ = raw_vs_published(
            21.33, 3.69, 11016, THRESHOLD, basis=PUBLISHED_BASIS_LIMITED_MASK
        )
        assert disp == DISP_PUBLISHED_UNKNOWN

    def test_selection_bias_still_outranks_the_basis(self):
        disp, _ = raw_vs_published(
            21.33, None, 0, THRESHOLD, graded_share=0.2,
            basis=PUBLISHED_BASIS_LIMITED_MASK, mask_mce=3.0, mask_n=500,
        )
        assert disp == DISP_NOT_PROVABLE


class TestTheCanonicalComparisonStands:
    def test_events_keep_a_published_number_and_its_dispositions(self):
        assert published_basis("events") == PUBLISHED_BASIS_CANONICAL
        rows = [dict(_weather_row(8, 1000, 300, 850.0), provenance="events",
                     pub_n=300, pub_winners=255, pub_sum_prob=255.0)]
        c = _cohort(rows, provenance="events")
        assert c["published_basis"] == PUBLISHED_BASIS_CANONICAL
        assert c["published_n"] == 300 and c["published_mce"] < 1.0
        disp, _ = raw_vs_published(
            c["mce"], c["published_mce"], c["published_n"], THRESHOLD,
            basis=c["published_basis"],
        )
        assert disp == DISP_EXCLUSION_WORKING

    @pytest.mark.parametrize("provenance", ["futures", None, "unknown"])
    def test_anything_else_is_a_limited_mask(self, provenance):
        assert published_basis(provenance) == PUBLISHED_BASIS_LIMITED_MASK


def test_the_mining_scan_itself_is_unchanged():
    """The correction is in labelling and judgment; the scan still computes the
    same complement (pub_n), so raw accounting and union coverage are intact."""
    for col in ("pub_n", "pub_winners", "pub_sum_prob", "any_known_n"):
        assert col in _FUTURES_MINING_SQL
