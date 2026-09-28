"""#9428: a graded prop reads "2 — miss", not "2.0 — miss".

`_sum_prop_stats` (the box-score grader) accumulates in `float`, so every
integral count reached `_build_props_script` as `2.0` and the WHAT HIT board
printed it verbatim — 559 of 559 graded rows on /events/14780548 (Rams @
Broncos, 2026-09-27). The fixtures in `test_props_script.py` pass `actual=2`
(an int), which is why no existing test ever saw the float.

These tests feed the label builder the REAL producer's output, not a literal.
"""

from app.routes.events import _build_props_script
from app.tasks.backfill_winners import _sum_prop_stats


def _row(actual, hit):
    return {
        "market_name": "LAR at DEN: Matthew Stafford Passing Touchdowns",
        "outcome_name": "Matthew Stafford: 3+",
        "over_probability": 0.0,
        "pregame_mark": 0.3,
        "hit": hit,
        "actual": actual,
    }


def test_the_grader_really_returns_a_float():
    # The premise. If the grader ever returns an int this file's reason to
    # exist is gone — and the label must still be right (next test).
    total = _sum_prop_stats({"passingTouchdowns": "2"}, ["passingTouchdowns"])
    assert total == 2.0
    assert isinstance(total, float)


def test_an_integral_count_from_the_grader_prints_without_a_decimal():
    total = _sum_prop_stats({"passingTouchdowns": "2"}, ["passingTouchdowns"])
    row = _build_props_script([_row(total, False)])[0]
    assert row["graded_label"] == "2 — miss"


def test_a_zero_prints_as_zero():
    total = _sum_prop_stats({"receivingYards": 0}, ["receivingYards"])
    row = _build_props_script([_row(total, False)])[0]
    assert row["graded_label"] == "0 — miss"


def test_a_composite_sum_prints_without_a_decimal():
    total = _sum_prop_stats(
        {"rushingYards": "88", "receivingYards": "61"},
        ["rushingYards", "receivingYards"],
    )
    row = _build_props_script([_row(total, True)])[0]
    assert row["graded_label"] == "149 — hit"


def test_a_real_fraction_keeps_its_decimals():
    # Nothing in the NFL vocabulary is fractional, but innings pitched is
    # (6.1). The rule strips a `.0`, never a digit.
    row = _build_props_script([_row(6.1, True)])[0]
    assert row["graded_label"] == "6.1 — hit"


def test_string_actuals_are_untouched():
    # Period-window verdicts publish their own prose ("6–1", "0 runs").
    row = _build_props_script([_row("6–1", True)])[0]
    assert row["graded_label"] == "6–1 — hit"


def test_an_int_actual_is_unchanged():
    row = _build_props_script([_row(2, True)])[0]
    assert row["graded_label"] == "2 — hit"
