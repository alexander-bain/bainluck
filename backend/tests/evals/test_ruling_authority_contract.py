import json
from pathlib import Path

from backend.scripts.evals.ruling_authority_contract import verdict


FIXTURES = Path(__file__).parent / "fixtures" / "ruling_authority_contract.json"


def test_fixture_corpus_matches_authority_oracle():
    for case in json.loads(FIXTURES.read_text()):
        assert verdict(**case["input"]) == case["expected"], case["id"]


def test_no_open_or_inferred_decision_can_be_accepted():
    for state in ("open", "inferred", "ambiguous"):
        for attributed in (False, True):
            for guarded in (False, True):
                assert verdict(decision_state=state, attributed_to_alex=attributed, ci_guarded=guarded)["verdict"] == "REFUSE"


def test_explicit_authority_is_required_for_acceptance():
    result = verdict(decision_state="explicit_approval", attributed_to_alex=True, ci_guarded=True)
    assert result == {"verdict": "ACCEPT", "reason": "explicit_authority"}
