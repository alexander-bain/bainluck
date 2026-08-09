import json
from pathlib import Path

from scripts.evals.prop_divergence_grouping_contract import render_plan


FIXTURE = Path(__file__).parent / "fixtures" / "prop_divergence_grouping_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        actual = render_plan(case["input"])
        assert actual == case["expected"], case["id"]


def test_settled_rows_never_enter_unchanged_drawer():
    case = next(row for row in pack()["cases"] if row["id"] == "settled-flat-is-visible")
    result = render_plan(case["input"])
    assert result["groups"][0]["collapsed"] == []
    assert result["groups"][0]["visible"] == ["graded"]


def test_cross_family_global_order_is_enforced():
    case = next(row for row in pack()["cases"] if row["id"] == "family-block-breaks-global-rank")
    assert "GLOBAL_DIVERGENCE_ORDER_DRIFT" in render_plan(case["input"])["reasons"]


def test_scale_case_retains_all_rows():
    items = [{"id":f"r{i}","key":f"M: F{i % 3}|row {i}","pregame_mark":0.5,"current":0.5 + (i % 5) / 100} for i in range(81)]
    result = render_plan({"state":"script","items":items})
    assert sum(len(group["visible"]) + len(group["collapsed"]) for group in result["groups"]) == 81
