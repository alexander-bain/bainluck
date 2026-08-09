import json

from scripts.evals.search_dropdown_cross_surface_contract import DEFAULT_FIXTURES, evaluate, evaluate_pack


def test_all_cross_surface_cases_match_the_oracle() -> None:
    result = evaluate_pack(json.loads(DEFAULT_FIXTURES.read_text()))
    assert result["passed"] == result["cases"] == 12


def test_team_promotion_must_be_shared_not_desktop_only() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "current-mobile-team-order-drift")
    result = evaluate(case["input"])
    assert result["desktop_order"][0] == "team"
    assert result["mobile_order"][0] == "future"
    assert "ORDER_PARITY_DRIFT" in result["errors"]


def test_exposure_and_click_analytics_are_separate_parity_gates() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {row["id"]: evaluate(row["input"]) for row in pack["cases"]}
    assert rows["answer-analytics-drift"]["errors"] == ["ANSWER_ANALYTICS_PARITY_DRIFT"]
    assert rows["click-analytics-drift"]["errors"] == ["CLICK_ANALYTICS_PARITY_DRIFT"]


def test_mobile_rows_are_exposed_as_options() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "mobile-option-semantics")
    assert evaluate(case["input"])["errors"] == ["MOBILE_OPTIONS_NOT_EXPOSED"]
