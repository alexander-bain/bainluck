"""The shared served-window predicate — one implementation, two callers.

`served_window_quality` exists because the census and the audit script both need
"grade the first twenty cards AS SERVED", and doctrine clause 5 is one
predicate, one implementation. Two copies of a window definition is how the
futures-only window and the served window drifted apart in the first place, and
that drift is what let a control targeting the served page be graded by an
instrument aimed at a different twenty cards.
"""

from __future__ import annotations

from app.utils.feed_quality_debug import served_window_quality

LADDER = "Will Meta (META) close above $540 on August 19?"


def _futures(name: str, market_id: int) -> dict:
    return {
        "type": "futures",
        "data": {
            "name": name,
            "market_id": market_id,
            "id": market_id,
            "category": "economics",
            "outcomes": [{"name": "Yes", "probability": 0.42}],
        },
    }


def _bundle(idx: int) -> dict:
    return {"type": "bundle", "data": {"name": f"Bundle {idx}", "id": 9000 + idx}}


def test_bundles_occupy_slots_and_push_futures_past_the_window():
    served = [_bundle(i) for i in range(5)]
    served += [_futures(f"Clean {i}?", i) for i in range(16)]
    served += [_futures(LADDER, 500)]

    report = served_window_quality(served, top_n=20)

    assert report["slots"] == 20
    assert report["futures_in_window"] == 15
    assert report["non_futures_in_window"] == 5
    assert report["boring_count"] == 0
    assert report["types"] == {"bundle": 5, "futures": 15}


def test_an_offender_inside_the_window_is_reported_with_its_reasons():
    served = [_bundle(0), _futures(LADDER, 500)]
    served += [_futures(f"Clean {i}?", i) for i in range(25)]

    report = served_window_quality(served, top_n=20)

    assert report["boring_count"] == 1
    row = report["boring"][0]
    assert row["name"] == LADDER
    assert row["quality_class"] in ("low_quality", "suppress")
    assert row["reasons"]


def test_the_denominator_is_slots_not_futures():
    served = [_bundle(i) for i in range(15)]
    served += [_futures(f"Clean {i}?", i) for i in range(20)]

    report = served_window_quality(served, top_n=20)

    assert report["slots"] == 20
    assert report["futures_in_window"] == 5


def test_a_short_page_reports_the_slots_it_actually_has():
    served = [_bundle(0), _futures("Clean?", 1)]

    report = served_window_quality(served, top_n=20)

    assert report["slots"] == 2
    assert report["futures_in_window"] == 1


def test_an_all_bundle_window_grades_zero_offenders_over_real_slots():
    """No futures to grade is not the same as a clean page — the slots are real."""
    served = [_bundle(i) for i in range(20)]

    report = served_window_quality(served, top_n=20)

    assert report["slots"] == 20
    assert report["futures_in_window"] == 0
    assert report["boring_count"] == 0
    assert report["non_futures_in_window"] == 20


def test_the_window_label_names_its_size():
    served = [_futures(f"Clean {i}?", i) for i in range(30)]

    assert served_window_quality(served, top_n=20)["window"] == "served_top20"
    assert served_window_quality(served, top_n=10)["window"] == "served_top10"
