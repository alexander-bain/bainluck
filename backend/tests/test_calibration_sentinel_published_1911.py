"""#1911 (CAL-P065) — the sentinel gets a PUBLISHED-curve view beside RAW MCE.

The sentinel mines the raw, un-excluded population; its own mining docstring
says so. It therefore had no view of the curve users actually read, and a
cohort a shipped exclusion ALREADY FIXES filed at full raw severity: #1142
went in as a P1 at 21.33pp raw against 3.69pp published, under a 5.0pp
threshold.

The issue's own acceptance is the spine of this file:

  * every filed cell body carries RAW **and** PUBLISHED, both with their n;
  * #1142 re-derives as 21.33 / 3.69 and does **not** file;
  * #1143 re-derives as raw / 7.57 published and **does** file — the other
    direction, same family, still genuinely over threshold (asserting both is
    the point; a guard tested one way is gotcha #43);
  * a synthetic cohort whose exclusion makes the curve *worse* files as a new
    class.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_sentinel import (
    DISP_EXCLUSION_HARMS,
    DISP_EXCLUSION_WORKING,
    DISP_PUBLISHED_UNKNOWN,
    DISP_REAL_BREAK,
    PUBLISHED_MIN_N,
    SENTINEL_MCE_THRESHOLD,
    _EVENTS_MINING_SQL,
    _FUTURES_MINING_SQL,
    _finalize_cohort,
    _fold_row_into_cohort,
    _new_cohort,
    build_issue_body,
    raw_vs_published,
)

THRESHOLD = 5.0


# ---------------------------------------------------------------------------
# The four dispositions
# ---------------------------------------------------------------------------


def test_1142_the_specimen_does_not_file():
    """The measured cell: raw 21.33pp, published 3.69pp, threshold 5.0pp."""
    disp, why = raw_vs_published(21.33, 3.69, 11016, THRESHOLD)
    assert disp == DISP_EXCLUSION_WORKING
    assert "21.33" in why and "3.69" in why


def test_1143_the_other_direction_still_files():
    """Same family, published number still over threshold. If only the #1142
    case were asserted, silencing the instrument entirely would pass."""
    disp, why = raw_vs_published(19.0, 7.57, 8000, THRESHOLD)
    assert disp == DISP_REAL_BREAK
    assert "7.57" in why


def test_an_exclusion_that_makes_the_curve_worse_is_its_own_class():
    """The third case — the one worth the build. Raw UNDER, published OVER.
    Nothing in the codebase looked for this before."""
    disp, why = raw_vs_published(3.1, 9.4, 5000, THRESHOLD)
    assert disp == DISP_EXCLUSION_HARMS
    assert "WORSE" in why


def test_both_under_threshold_is_healthy():
    disp, _ = raw_vs_published(2.0, 1.4, 5000, THRESHOLD)
    assert disp == DISP_EXCLUSION_WORKING


def test_a_published_curve_too_small_to_judge_is_absent_not_zero():
    """Gotcha #54. An exclusion leaving 9 rows behind has not produced a
    well-calibrated cell; reporting 0.0pp would be the loudest false all-clear
    available."""
    disp, why = raw_vs_published(21.33, None, 9, THRESHOLD)
    assert disp == DISP_PUBLISHED_UNKNOWN
    assert "too few" in why
    assert "21.33" in why  # the raw number is still stated, not swallowed


def test_a_missing_raw_mce_does_not_invent_a_disposition():
    disp, _ = raw_vs_published(None, 3.0, 5000, THRESHOLD)
    assert disp == DISP_PUBLISHED_UNKNOWN


# ---------------------------------------------------------------------------
# Coverage cannot substitute for this — the reason no threshold tuning works
# ---------------------------------------------------------------------------


def test_coverage_and_disposition_are_independent_quantities():
    """#1911's central claim, as an assertion.

    Coverage counts EXCLUDED rows; the disposition depends on what the
    REMAINING rows do. The two are not related by a fraction, so no coverage
    threshold can stand in for the published number. Two cohorts with the SAME
    coverage and opposite dispositions is the proof.
    """
    # Identical exclusion coverage (say 23%), opposite outcomes.
    fixed = raw_vs_published(21.33, 3.69, 11016, THRESHOLD)[0]
    broken = raw_vs_published(21.33, 18.9, 11016, THRESHOLD)[0]
    assert fixed == DISP_EXCLUSION_WORKING
    assert broken == DISP_REAL_BREAK


# ---------------------------------------------------------------------------
# The mining pass computes both from ONE predicate
# ---------------------------------------------------------------------------


def test_the_published_aggregate_is_the_negation_of_the_same_union():
    """Raw and published must be two sides of ONE predicate. Two hand-written
    copies would let an edit to one silently compare different populations."""
    assert "any_known_n" in _FUTURES_MINING_SQL
    for col in ("pub_n", "pub_winners", "pub_sum_prob"):
        assert col in _FUTURES_MINING_SQL, col
    # Count the RENDERED union fragment, not a clause inside it: the esports
    # clause also appears once on its own as the `esports_bundle_n` per-class
    # SUM, so a clause-level count answers a different question (5, not 4).
    from app.tasks.calibration_sentinel import (
        _HEURISTIC_SOURCES,
        _KNOWN_UNION_SQL,
        _VOID_SOURCES,
        _in_list,
    )

    rendered = _KNOWN_UNION_SQL.format(
        void_in=_in_list(_VOID_SOURCES),
        heuristic_in=_in_list(_HEURISTIC_SOURCES),
    )
    # Four sites: any_known_n, pub_n, pub_winners, pub_sum_prob — all from the
    # one fragment, which is the property that stops raw and published drifting.
    assert _FUTURES_MINING_SQL.count(rendered) == 4


def test_events_report_a_real_published_number_not_a_missing_one():
    """Events carry no per-outcome exclusion flags, so published == raw. It
    must be emitted explicitly: a missing column would read as 'under
    threshold' and silently suppress every events cohort."""
    for col in ("pub_n", "pub_winners", "pub_sum_prob", "any_known_n"):
        assert col in _EVENTS_MINING_SQL, col


# ---------------------------------------------------------------------------
# End-to-end through the real fold/finalize path
# ---------------------------------------------------------------------------


def _row(bucket, n, winners, sum_prob, pub_n, pub_winners, pub_sum_prob):
    return {
        "source": "kalshi", "category": "basketball", "series_family": "KXNBA",
        "structure_class": "binary", "provenance": "futures",
        "bucket": bucket, "n": n, "winners": winners, "sum_prob": sum_prob,
        "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
        "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": n - pub_n,
        "any_known_n": n - pub_n,
        "pub_n": pub_n, "pub_winners": pub_winners, "pub_sum_prob": pub_sum_prob,
        "min_created_at": None,
    }


def _cohort_from(rows):
    key = (("provenance", "futures"), ("source", "kalshi"), ("category", "basketball"))
    c = _new_cohort(key, rows[0])
    for r in rows:
        _fold_row_into_cohort(c, r)
    return _finalize_cohort(c, now_ts=0.0)


def test_fold_and_finalize_produce_both_numbers():
    """The #1142 shape driven through the real accumulation path: a high band
    where the EXCLUDED rows carry all the miscalibration."""
    rows = [
        # bucket 8 (cp~0.85): 1000 raw outcomes, only 300 win -> badly raw-miscal.
        # 700 of those are excluded prop-threshold rows and they are the bad ones;
        # the 300 that survive win 255 (85%) -> published is well calibrated.
        _row(8, 1000, 300, 850.0, pub_n=300, pub_winners=255, pub_sum_prob=255.0),
    ]
    c = _cohort_from(rows)
    assert c["total_n"] == 1000
    assert c["published_n"] == 300
    assert c["mce"] > 10.0            # raw looks terrible
    assert c["published_mce"] < 1.0   # published is fine

    disp, _ = raw_vs_published(
        c["mce"], c["published_mce"], c["published_n"], SENTINEL_MCE_THRESHOLD
    )
    assert disp == DISP_EXCLUSION_WORKING


def test_finalize_refuses_a_published_mce_below_the_n_floor():
    rows = [_row(8, 1000, 300, 850.0, pub_n=10, pub_winners=8, pub_sum_prob=8.5)]
    c = _cohort_from(rows)
    assert c["published_n"] == 10 < PUBLISHED_MIN_N
    assert c["published_mce"] is None


def test_finalize_computes_a_published_mce_at_the_floor():
    """Boundary pinned in both directions so a later `<` -> `<=` slip is caught."""
    rows = [_row(8, 1000, 300, 850.0,
                 pub_n=PUBLISHED_MIN_N, pub_winners=170,
                 pub_sum_prob=PUBLISHED_MIN_N * 0.85)]
    c = _cohort_from(rows)
    assert c["published_mce"] is not None


# ---------------------------------------------------------------------------
# The body carries both — #1911's first acceptance criterion
# ---------------------------------------------------------------------------


def _body_cohort(mce, published_mce, published_n, disposition, why):
    return {
        "dims": {"source": "kalshi", "category": "basketball"},
        "cohort_key": (("source", "kalshi"), ("category", "basketball")),
        "fingerprint": "abc123",
        "mce": mce,
        "total_n": 14315,
        "published_mce": published_mce,
        "published_n": published_n,
        "disposition": disposition,
        "disposition_why": why,
        "provenance": "futures",
        "category": "basketball",
        "is_new_format": False,
        "hook_signature": False,
        "buckets": [
            {"bucket": i, "n": 0, "winners": 0, "sum_prob": 0.0} for i in range(10)
        ],
        "overlap_fractions": {"kalshi_prop_threshold": 0.231, "any_known": 0.241},
    }


def test_every_filed_body_carries_raw_and_published_with_their_n():
    body = build_issue_body(
        _body_cohort(21.33, 3.69, 11016, DISP_EXCLUSION_WORKING, "because"),
        "kalshi_prop_threshold", 0.241,
    )
    assert "21.33pp" in body
    assert "3.69pp" in body
    assert "14315" in body   # raw n
    assert "11016" in body   # published n
    assert "RAW" in body and "PUBLISHED" in body


def test_an_absent_published_number_says_so_in_the_body():
    body = build_issue_body(
        _body_cohort(21.33, None, 9, DISP_PUBLISHED_UNKNOWN, "too few"),
        None, 0.0,
    )
    assert "not computable" in body
    assert "ABSENT" in body
    assert "0.00pp" not in body  # never a flattering zero


def test_the_harms_class_gets_its_own_loud_section():
    body = build_issue_body(
        _body_cohort(3.1, 9.4, 5000, DISP_EXCLUSION_HARMS,
                     "an exclusion is removing good rows"),
        None, 0.0,
    )
    assert "MAKING THIS CURVE WORSE" in body
    assert "Do not tune coverage" in body


def test_a_working_exclusion_body_does_not_shout_the_harms_warning():
    """Both directions (gotcha #43): the new section must not appear on every
    finding, or it stops meaning anything."""
    body = build_issue_body(
        _body_cohort(21.33, 3.69, 11016, DISP_EXCLUSION_WORKING, "fine"),
        "kalshi_prop_threshold", 0.241,
    )
    assert "MAKING THIS CURVE WORSE" not in body
