import json
from pathlib import Path

from scripts.evals.interestingness_temporal_holdout_contract import evaluate_case, evaluate_corpus


FIXTURE = Path(__file__).parent / "fixtures" / "interestingness_temporal_holdout_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        actual = evaluate_case(case)
        assert actual["verdict"] == case["expected"]["verdict"], case["id"]
        assert actual["reasons"] == case["expected"]["reasons"], case["id"]


def test_clean_fixture_measures_holdout_only_and_clears_floor():
    result = evaluate_case(pack()["cases"][0])
    assert result["train_rows"] == 2
    assert result["holdout_rows"] == 4
    assert result["baseline_precision_at_k"] == 0.5
    assert result["candidate_precision_at_k"] == 1.0
    assert result["delta_points"] == 50.0


def test_ties_are_deterministic_under_input_reversal():
    case = next(row for row in pack()["cases"] if row["id"] == "deterministic-tie")
    forward = evaluate_case(case)
    case["rows"].reverse()
    reverse = evaluate_case(case)
    assert forward == reverse


def test_corpus_has_required_failure_classes():
    results = evaluate_corpus(pack())
    reasons = {reason for result in results for reason in result["reasons"]}
    assert {
        "ITEM_LEAKAGE",
        "FIT_NOT_TRAIN_ONLY",
        "EVAL_NOT_HOLDOUT_ONLY",
        "WRONG_TIME_AUTHORITY",
        "BASELINE_POPULATION_MISMATCH",
        "CANDIDATE_POPULATION_MISMATCH",
        "HOLDOUT_TOO_SMALL",
        "HOLDOUT_ONE_CLASS",
    } <= reasons
