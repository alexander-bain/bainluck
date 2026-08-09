import copy
import json
from pathlib import Path

from backend.scripts.evals.statistical_claim_authority import evaluate_statistical_claim, holm_rejections


FIXTURES = Path(__file__).parent / "fixtures" / "statistical_claim_authority.json"


def pack():
    return json.loads(FIXTURES.read_text())


def test_valid_clustered_preregistered_claim_accepts():
    assert evaluate_statistical_claim(pack()["valid"]) == {"verdict": "ACCEPT", "reasons": []}


def test_every_adversary_bites():
    for case in pack()["adversaries"]:
        claim = copy.deepcopy(pack()["valid"])
        claim.update(case.get("set", {}))
        claim.update(case.get("extra", {}))
        result = evaluate_statistical_claim(claim)
        assert case["reason"] in result["reasons"], (case["id"], result)


def test_holm_preserves_original_order_and_stops_after_first_failure():
    assert holm_rejections([0.04, 0.001, 0.02]) == [True, True, True]
    assert holm_rejections([0.01, 0.04, 0.049]) == [True, False, False]


def test_single_preregistered_comparison_needs_no_multiplicity_penalty():
    claim = copy.deepcopy(pack()["valid"])
    claim.update(comparison_family=1, p_values=[0.04], target_index=0)
    assert "MULTIPLE_COMPARISON_NOT_SIGNIFICANT" not in evaluate_statistical_claim(claim)["reasons"]


def test_missing_contract_fails_closed():
    assert evaluate_statistical_claim({}) == {"verdict": "REFUSE", "reasons": ["STAT_FIELDS_MISSING"]}
