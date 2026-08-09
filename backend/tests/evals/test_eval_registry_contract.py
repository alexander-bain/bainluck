import json
from pathlib import Path

from scripts.evals.eval_registry_contract import validate


HERE = Path(__file__).parent
CASES = HERE / "fixtures" / "eval_registry_contract.json"
REGISTRY = HERE.parent.parent / "scripts" / "evals" / "eval_registry.json"


def test_registry_itself_is_valid():
    assert validate(json.loads(REGISTRY.read_text())) == {"verdict": "ALLOW", "errors": []}


def test_every_adversary_matches_the_oracle():
    for case in json.loads(CASES.read_text())["cases"]:
        assert validate(case["registry"], case.get("changed")) == case["expected"], case["id"]


def test_new_artifact_must_join_a_domain():
    base = json.loads(REGISTRY.read_text())
    assert validate(base, ["brand_new_oracle"])["errors"] == ["CHANGED_ARTIFACT_UNREGISTERED"]


def test_recent_codex_contracts_are_registered():
    base = json.loads(REGISTRY.read_text())
    recent = [
        "measurement_surface_truth_contract",
        "politics_cache_tier_contract",
        "additional_markets_authority_contract",
        "matched_calibration_evidence_contract",
    ]
    assert validate(base, recent) == {"verdict": "ALLOW", "errors": []}
