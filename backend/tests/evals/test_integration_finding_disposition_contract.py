import json
from pathlib import Path

from backend.scripts.evals.integration_finding_disposition_contract import disposition


FIXTURES = Path(__file__).parent / "fixtures" / "integration_finding_disposition_contract.json"


def test_fixture_corpus_matches_disposition_oracle():
    for case in json.loads(FIXTURES.read_text()):
        assert disposition(**case["input"]) == case["expected"], case["id"]


def test_a_test_corpus_does_not_turn_an_unrepaired_finding_green():
    result = disposition(finding_severity="P1", applies_to_head=True, repaired=False, explicitly_overruled=False, overruling_authority=None, regression_test_wired=True)
    assert result == {"verdict": "REFUSE", "reason": "blocking_finding_unresolved"}


def test_integrator_cannot_silently_overrule_product_risk():
    result = disposition(finding_severity="P1", applies_to_head=True, repaired=False, explicitly_overruled=True, overruling_authority="integrator", regression_test_wired=False)
    assert result["verdict"] == "REFUSE"
