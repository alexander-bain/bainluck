"""The P4-tail grader, driven off fixtures at ZERO horizon cost.

LAT-P080B builds this the way LAT-P080A built `grade_ruling_110.py`: the ≥6 h
horizon read has been defeated five times and the sixth runs under a bought
deploy freeze, so nothing that can be decided before the window is decided in
it. The morning window's whole P4-tail step becomes one command.

🔴 **AND EVERY STATE IS EXERCISED, NOT JUST TODAY'S.** A grader whose only
fixture is the payload it will actually see grades one state and silently cannot
distinguish the others — which is the defect the falsifier itself shipped with
(`samples: 0` read as a measurement, #2071). `MIXED_RING`, `INSUFFICIENT_
SAMPLES`, `UNREADABLE`, `CONSTANT_STALE`, `TAIL_CONFIRMED_OVER_TTL` and
`NOT_REFUTED` are each proven to fire.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import grade_p4_tail as g  # noqa: E402

from app.utils.typeahead_beat_budget import (  # noqa: E402
    MEASURED_WALL_MAX_S,
    RESPONSE_CACHE_TTL_S,
)

BLEND = "blend:query_log+trending:20/40_from_log"
DB_ONLY = "db:search_query_logs:30d"
ZSET_ONLY = "redis:search:trending:24h"


def _rec(wall, source=BLEND, terminal="complete"):
    return {
        "at": 1_787_000_000.0,
        "terminal": terminal,
        "seconds_wall": wall,
        "period_s": 60.0,
        "head_source": source,
    }


def _payload(records, status="ok"):
    return {
        "status": status,
        "ring_max": 32,
        "response_cache_ttl_s": RESPONSE_CACHE_TTL_S,
        "passes": {"n": len(records), "records": records},
    }


def _full_post_fix(wall, n=32, source=BLEND):
    return _payload([_rec(wall, source) for _ in range(n)])


# ---------------------------------------------------------------------------
# The arm split — and the hazard THIS cycle put into it.
# ---------------------------------------------------------------------------


def test_a_db_only_head_counts_as_POST_FIX_not_pre_fix():
    """🔴 The #2072 interaction, and it would have silently shrunk the arm.

    LAT-P080B hour-buckets the trending zset, so for roughly the first hour
    after that deploy the window is thin and `resolve_head` returns
    `db:search_query_logs:30d` rather than `blend:...`. Defining post-fix as
    "starts with blend:" would classify those as PRE-FIX and under-count the one
    arm whose sample size is the entire problem — turning a gradeable ring into
    a MIXED_RING and sending the window home with nothing.
    """
    assert g.classify_arm(DB_ONLY) == "post_fix"
    assert g.classify_arm(BLEND) == "post_fix"


def test_the_zset_only_cascade_and_the_floor_are_PRE_FIX():
    assert g.classify_arm(ZSET_ONLY) == "pre_fix"
    assert g.classify_arm("static_floor") == "pre_fix"


def test_an_unrecognised_head_source_is_UNKNOWN_and_joins_neither_arm():
    """Folding it in would put a record the grader does not understand into the
    sample whose size is the question."""
    for value in ("something_new", "", None, 17):
        assert g.classify_arm(value) == "unknown"


def test_a_record_with_no_wall_is_COUNTED_rather_than_silently_dropped():
    """An unexplained shortfall in n reads as 'the freeze was short'."""
    split = g.split_ring(_payload([_rec(40.0), _rec(None), _rec(42.0)]))
    assert split["records_total"] == 3
    assert split["records_without_a_wall"] == 1
    assert split["post_fix"]["n"] == 2


# ---------------------------------------------------------------------------
# The six verdicts, each proven to fire.
# ---------------------------------------------------------------------------


def test_a_mixed_ring_refuses_to_grade():
    records = [_rec(40.0) for _ in range(28)] + [_rec(52.0, ZSET_ONLY) for _ in range(4)]
    grade = g.grade_tail(_payload(records))

    assert grade["verdict"] == "MIXED_RING"
    assert "horizon has not been reached" in grade["reason"]
    assert g.exit_code_for(grade["verdict"]) == g.EXIT_UNREADABLE


def test_lat_p079s_own_n8_arm_is_still_INSUFFICIENT():
    """The clause exists because n=8 could not speak to the tail. It still cannot."""
    grade = g.grade_tail(_full_post_fix(45.952, n=8))

    assert grade["verdict"] == "INSUFFICIENT_SAMPLES"
    assert "n=8" in grade["reason"]
    assert g.exit_code_for(grade["verdict"]) == g.EXIT_UNREADABLE


def test_an_unreadable_payload_is_never_a_tail_measurement():
    for status in ("unreadable", "no_data"):
        grade = g.grade_tail(_payload([], status=status))
        assert grade["verdict"] == "UNREADABLE"
        assert status in grade["reason"]


def test_a_post_fix_max_above_the_pinned_constant_is_the_FIFTH_stale_instance():
    grade = g.grade_tail(_full_post_fix(MEASURED_WALL_MAX_S + 3.0))

    assert grade["verdict"] == "CONSTANT_STALE"
    assert "fifth instance" in grade["reason"]
    assert g.exit_code_for(grade["verdict"]) == g.EXIT_CONSTANT_STALE


def test_a_wall_over_the_ttl_but_under_the_constant_CONFIRMS_the_tail():
    """The expected outcome if nothing changed: still marginal, nothing owed."""
    wall = (RESPONSE_CACHE_TTL_S + MEASURED_WALL_MAX_S) / 2
    grade = g.grade_tail(_full_post_fix(wall))

    assert grade["verdict"] == "TAIL_CONFIRMED_OVER_TTL"
    assert grade["still_exceeds_ttl"] is True
    assert g.exit_code_for(grade["verdict"]) == g.EXIT_TAIL_CONFIRMED


def test_a_favourable_read_is_NOT_REFUTED_and_never_says_improved():
    """🔴 Ruling 075's trap, closed at the point of writing.

    Four consecutive cycles proved a prior sampled maximum too low. A lower read
    is consistent with a smaller sample of the same distribution, so the
    favourable verdict must not be phrasable as a win.
    """
    grade = g.grade_tail(_full_post_fix(45.0))

    assert grade["verdict"] == "NOT_REFUTED"
    assert grade["still_exceeds_ttl"] is False
    assert "NOT 'THE TAIL IMPROVED'" in grade["reason"]
    assert "improved" not in grade["reason"].replace("THE TAIL IMPROVED", "")
    assert g.exit_code_for(grade["verdict"]) == g.EXIT_OK


def test_no_verdict_anywhere_recommends_lowering_the_constant():
    """Trap 2, asserted across EVERY state rather than on the tempting one.

    The favourable read is where a reader wants to lower it, but a grader that
    only refuses there has a hole in every other branch.
    """
    payloads = [
        _full_post_fix(45.0),
        _full_post_fix(66.0),
        _full_post_fix(MEASURED_WALL_MAX_S + 3.0),
        _full_post_fix(45.0, n=8),
        _payload([], status="unreadable"),
    ]
    for payload in payloads:
        grade = g.grade_tail(payload)
        assert "LOWERING MEASURED_WALL_MAX_S" in grade["never_recommend"]
        assert "lower" not in grade["reason"].lower() or "lower bound" in grade["reason"].lower()


# ---------------------------------------------------------------------------
# The instrument's own integrity.
# ---------------------------------------------------------------------------


def test_the_grader_imports_its_thresholds_and_does_not_re_type_them():
    """A second copy of MEASURED_WALL_MAX_S is a second thing to go stale —
    which is the exact defect class this clause exists to close."""
    src = (Path(__file__).resolve().parents[1] / "scripts" / "grade_p4_tail.py").read_text()
    assert "from app.utils.typeahead_beat_budget import" in src
    assert f"= {MEASURED_WALL_MAX_S}" not in src, "the constant is re-typed here"

    grade = g.grade_tail(_full_post_fix(45.0))
    assert grade["pinned"]["measured_wall_max_s"] == MEASURED_WALL_MAX_S
    assert grade["pinned"]["response_cache_ttl_s"] == RESPONSE_CACHE_TTL_S


def test_the_four_raised_maxima_travel_in_the_report_as_the_sampling_argument():
    """Carried as data so the report PRINTS the argument rather than asserting it."""
    grade = g.grade_tail(_full_post_fix(45.0))
    assert grade["pinned"]["max_history_s"] == [42.6, 53.920, 61.282, 66.365]
    assert grade["pinned"]["lat_p079_post_fix_arm"]["n"] == 8


def test_the_sample_bar_is_below_the_baseline_depth_but_not_trivially_so():
    """A bar at or above 32 could never be met by a 32-deep ring with one gap;
    a bar near zero would re-admit the n=8 arm the clause rejects."""
    assert g.MIN_TAIL_SAMPLES < g.BASELINE_TAIL_SAMPLES
    assert g.MIN_TAIL_SAMPLES > g.LAT_P079_POST_FIX_ARM["n"] * 2


@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("NOT_REFUTED", 0),
        ("TAIL_CONFIRMED_OVER_TTL", 1),
        ("CONSTANT_STALE", 2),
        ("MIXED_RING", 3),
        ("INSUFFICIENT_SAMPLES", 3),
        ("UNREADABLE", 3),
    ],
)
def test_exit_codes_follow_gotcha_54s_amendment(verdict, expected):
    """`1` is a result; anything else is a story about the harness — except `2`,
    which is a same-window obligation deliberately not wearing `1`'s clothes."""
    assert g.exit_code_for(verdict) == expected


def test_the_p95_index_does_not_walk_off_the_end_of_a_short_arm():
    """An off-by-one here would raise inside the window, on the one read the
    freeze was bought for."""
    for n in range(1, 6):
        stats = g._stats([float(i) for i in range(n)])
        assert stats["p95"] is not None
        assert stats["max"] == float(n - 1)


def test_an_empty_arm_reports_None_and_never_a_flattering_zero():
    """`max: 0.0` on a wall distribution is the most favourable number there is,
    and it would be a fabrication (gotcha #53)."""
    stats = g._stats([])
    assert stats == {"n": 0, "min": None, "p50": None, "p95": None, "max": None}
