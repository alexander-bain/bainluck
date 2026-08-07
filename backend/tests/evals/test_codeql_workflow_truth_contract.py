import json
from pathlib import Path

from backend.scripts.evals.codeql_workflow_truth_contract import evaluate, evaluate_plan


FIXTURES = Path(__file__).parent / "fixtures" / "codeql_workflow_truth_contract.json"


def test_fixture_corpus_matches_oracle():
    corpus = json.loads(FIXTURES.read_text())
    assert len(corpus["cases"]) >= 14
    for case in corpus["cases"]:
        assert evaluate(case) == case["expected"], case["id"]
    for plan in corpus["plans"]:
        assert evaluate_plan(plan) == plan["expected"], plan["id"]


def test_required_failure_modes_are_typed():
    corpus = json.loads(FIXTURES.read_text())
    reasons = {
        reason
        for case in corpus["cases"]
        for reason in case["expected"]["reason_codes"]
    }
    assert {
        "swift_requires_macos",
        "native_unscanned",
        "matrix_partial_success_masked",
        "missing_sarif_permission",
        "untrusted_code_with_write_token",
        "relevant_path_skipped",
        "mutable_action_ref",
        "generated_noise",
        "duplicate_scan_owner",
        "required_check_detached",
    } <= reasons


def test_clean_mixed_language_plan_passes():
    corpus = json.loads(FIXTURES.read_text())
    plan = next(p for p in corpus["plans"] if p["id"] == "clean_mixed_language_plan")
    assert evaluate_plan(plan) == {"verdict": "ALLOW", "reason_codes": []}

