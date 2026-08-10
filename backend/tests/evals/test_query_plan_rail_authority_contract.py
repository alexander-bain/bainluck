import json
from pathlib import Path

from scripts.evals.query_plan_rail_authority_contract import evaluate


FIXTURES = Path(__file__).parent / "fixtures" / "query_plan_rail_authority_contract.json"


def corpus():
    return json.loads(FIXTURES.read_text())


def test_corpus_matches_oracle():
    for case in corpus()["cases"]:
        assert evaluate(case) == case["expected"], case["id"]


def test_every_refusal_has_one_precise_reason():
    for case in corpus()["cases"]:
        result = evaluate(case)
        if result["verdict"] == "REFUSE":
            assert len(result["reasons"]) == 1, case["id"]


def test_both_select_side_effect_classes_are_pinned():
    ids = {case["id"] for case in corpus()["cases"]}
    assert {"select_pg_cancel_backend", "select_session_advisory_lock"} <= ids


def test_safe_plan_and_safe_analyze_are_distinct_acceptance_cases():
    accepted = {
        case["id"] for case in corpus()["cases"] if evaluate(case)["verdict"] == "ACCEPT"
    }
    assert accepted == {
        "safe_estimated_plan",
        "safe_analyzed_select_with_function_policy",
    }

