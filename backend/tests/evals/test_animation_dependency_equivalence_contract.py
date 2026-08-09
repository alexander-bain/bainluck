import json
from pathlib import Path

from scripts.evals.animation_dependency_equivalence_contract import evaluate
from scripts.evals.eval_registry_contract import validate


HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "animation_dependency_equivalence_contract.json"
REGISTRY = HERE.parent.parent / "scripts" / "evals" / "eval_registry.json"


def cases():
    return json.loads(FIXTURE.read_text())["cases"]


def test_every_case_matches_the_oracle():
    for case in cases():
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_optional_chunk_cannot_gate_first_card():
    case = next(c for c in cases() if c["id"] == "slow-feature-chunk")
    assert "ANIMATION_CHUNK_GATES_CONTENT" in evaluate(case["input"])["reasons"]


def test_failed_animation_chunk_fails_open_to_content():
    case = next(c for c in cases() if c["id"] == "feature-chunk-network-failure")
    assert "OPTIONAL_CHUNK_FAILURE_HIDES_CONTENT" in evaluate(case["input"])["reasons"]


def test_contract_is_registered_under_first_card_authority():
    registry = json.loads(REGISTRY.read_text())
    assert validate(registry, ["animation_dependency_equivalence_contract"]) == {
        "verdict": "ALLOW", "errors": []
    }
