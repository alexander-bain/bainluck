import json

from scripts.evals.calibration_independence_disclosure_contract import DEFAULT_FIXTURES, evaluate, evaluate_pack


def test_all_independence_cases_match_the_oracle() -> None:
    result = evaluate_pack(json.loads(DEFAULT_FIXTURES.read_text()))
    assert result["passed"] == result["cases"] == 12


def test_observation_count_never_substitutes_for_question_count() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "normalized-field-one-question")
    result = evaluate(case["input"])
    assert result["observations"] == 3
    assert result["independent_questions"] == 1


def test_partial_futures_identity_cannot_certify_whole_curve() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "futures-only-question-count-cannot-cover-whole-curve")
    result = evaluate(case["input"])
    assert result["independent_questions"] is None
    assert "QUESTION_IDENTITY_INCOMPLETE" in result["errors"]


def test_consequential_claims_require_clustered_uncertainty() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "current-public-disclosure-missing")
    result = evaluate(case["input"])
    assert "CORRELATED_ROWS_TREATED_INDEPENDENT" in result["errors"]
    assert "CLUSTERED_UNCERTAINTY_MISSING" in result["errors"]
