"""A throttled request is not a fast one (#2260, LAT-P110).

## Why this file exists

`cold_path_snapshot._classify()` read `X-Feed-Cache`, fell back to the query
count — `return "cold" if q > 0 else "warm"` — and **never looked at `http`**.

An HTTP 429 from the API's 60/minute-per-IP limiter carries no cache header,
executes zero queries, and answers in 2–3 ms with a real `x-response-time`. So
it took the fall-through and was graded as a **warm 2 ms search**, counted into
`n_graded`, and reported as though the search surface had been measured.

A canonical `needle_latency.py` run issues ~68 requests with the six cold
searches LAST, so the searches are precisely what gets refused — and a latency
lane throttles its own harness merely by issuing `db-query` EXPLAINs from the
same IP while it works.

The cost was a wrong diagnosis, not just a wrong cell. LAT-P109 parked P109-6,
"the needle's cold-search member went 6/6 WARM … cause NOT established", and
three consecutive needle refusals were filed as "the pool went warm" when for
that member the truth was "the pool went UNMEASURABLE". Different fact,
different owner: one is Alex's prewarm decision, the other is a bug in this
lane's own instrument.

## The shape of the guard

The fixtures below are the REAL production samples from
`LAT-P110-mid` — a genuine 429 as the harness recorded it, and a genuine
`shared_hit` beside it — not invented shapes. The whole defect was that a
hand-drawn "error sample" would have carried no `server_ms` and would have been
excluded by the old code anyway; the real one carries 3.0 ms and that is why it
got through.

Both directions (gotcha #43): a rejection must be excluded AND a served request
must still be graded exactly as before.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "cold_path_snapshot", _SCRIPTS / "cold_path_snapshot.py"
)
cps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cps)


#: Verbatim from `/tmp/needle-p110-mid.json`, `search_cold_samples[0]`. Note the
#: `server_ms`: the rate limiter answers fast and says so in a real header,
#: which is exactly why "has a server_ms" was not a sufficient test.
REAL_429 = {
    "path": "/api/events/search?q=kaiserslautern",
    "http": 429,
    "bytes": 0,
    "wall_ms": 230.8,
    "server_ms": 3.0,
    "feed_cache": None,
    "timing_split": "wall=2.4;db=0.0;app=2.4;q=0;maxq=0.0;router=3.6",
    "queries": 0,
    "term": "kaiserslautern",
}

#: Verbatim from the same run, `tab_samples["discover_native"][0]`.
REAL_SHARED_HIT = {
    "path": "/api/feed?limit=50&offset=0&event_pct=0.15",
    "http": 200,
    "bytes": 124259,
    "wall_ms": 544.7,
    "server_ms": 129.0,
    "feed_cache": "shared_hit",
    "queries": 7,
}

#: A genuinely cold non-feed endpoint: no cache header, real queries.
REAL_COLD_NO_HEADER = {
    "path": "/api/events/search?q=cremonese",
    "http": 200,
    "server_ms": 787.0,
    "feed_cache": None,
    "queries": 12,
}


# ---------------------------------------------------------------------------
# the defect
# ---------------------------------------------------------------------------


def test_a_429_is_not_graded_as_a_warm_search():
    assert cps._classify(REAL_429) == cps.REJECTED, (
        "the rate limiter was graded as a latency observation — this is the "
        "exact sample that produced LAT-P109's unexplained '6/6 WARM at 2-4 ms'"
    )


def test_a_429_would_have_been_called_warm_by_the_header_and_query_fallback():
    """The control. Without the status-code branch the fall-through says warm,
    so this test is what makes the one above mean something rather than restate
    an obvious truth."""
    assert (REAL_429["feed_cache"] or "") == ""
    assert REAL_429["queries"] == 0
    # ...which is precisely `return "cold" if q > 0 else "warm"`.
    assert ("cold" if REAL_429["queries"] > 0 else "warm") == "warm"


@pytest.mark.parametrize("code", [400, 401, 403, 429, 500, 502, 503, 504])
def test_every_non_200_is_rejected_not_just_429(code: int):
    """429 is the one that bit, but a 503 answered in 5 ms would grade as a fast
    warm request by the same route through the function."""
    assert cps._classify({**REAL_429, "http": code}) == cps.REJECTED


def test_a_transport_failure_is_rejected_too():
    assert (
        cps._classify(
            {"path": "/api/feed", "http": None, "error": "TimeoutError: timed out"}
        )
        == cps.REJECTED
    )


# ---------------------------------------------------------------------------
# the other direction — served requests must grade exactly as before
# ---------------------------------------------------------------------------


def test_a_served_warm_request_is_still_warm():
    assert cps._classify(REAL_SHARED_HIT) == "warm"


def test_a_served_cold_request_is_still_cold():
    assert cps._classify(REAL_COLD_NO_HEADER) == "cold"


def test_an_http_200_with_a_miss_header_is_still_cold():
    assert cps._classify({**REAL_SHARED_HIT, "feed_cache": "miss"}) == "cold"


def test_a_sample_with_no_http_key_at_all_still_classifies():
    """`_classify` is also called on rows assembled by older callers that never
    recorded a status. Absent must not mean rejected."""
    assert cps._classify({"feed_cache": "hit"}) == "warm"
    assert cps._classify({"feed_cache": None, "queries": 4}) == "cold"


# ---------------------------------------------------------------------------
# it has to reach the summary, not just the classifier
# ---------------------------------------------------------------------------


def _classified(rows: list[dict]) -> list[dict]:
    return [{**r, "class": cps._classify(r)} for r in rows]


def test_rejections_are_excluded_from_graded_and_counted_out_loud():
    rows = _classified([REAL_429] * 6 + [REAL_SHARED_HIT])
    summary = cps._summarize(rows)

    assert summary["n"] == 7
    assert summary["n_graded"] == 1, (
        "the six 429s were counted as graded samples — they carry a real "
        f"server_ms, which is how they got in: {summary}"
    )
    assert summary["n_rejected"] == 6
    assert summary["rejections"] == {"429": 6}
    # and the medians must describe only the served request
    assert summary["p50_all"] == 129.0
    assert summary["n_warm"] == 1
    assert summary["n_cold"] == 0


def test_an_all_rejected_member_yields_no_median_rather_than_a_fast_one():
    """The failure mode in one assertion: six throttled searches must produce
    NOTHING, not a 3 ms p50."""
    summary = cps._summarize(_classified([REAL_429] * 6))
    assert summary["n_graded"] == 0
    assert summary["p50_all"] is None
    assert summary["p50_cold"] is None
    assert summary["p50_warm"] is None
    assert summary["rejections"] == {"429": 6}


def test_rejection_counts_names_the_status_so_the_report_can_say_throttled():
    rows = _classified([REAL_429, {**REAL_429, "http": 503}, REAL_SHARED_HIT])
    assert cps.rejection_counts(rows) == {"429": 1, "503": 1}


def test_a_clean_run_reports_no_rejections():
    summary = cps._summarize(_classified([REAL_SHARED_HIT, REAL_COLD_NO_HEADER]))
    assert summary["n_rejected"] == 0
    assert summary["rejections"] == {}
    assert summary["n_graded"] == 2
