import json
from pathlib import Path

from scripts.evals.principal_bound_client_state_contract import evaluate


FIXTURES = Path(__file__).parent / "fixtures" / "principal_bound_client_state_contract.json"


def test_corpus_matches_oracle():
    cases = json.loads(FIXTURES.read_text())
    assert len(cases) >= 14
    for case in cases:
        assert evaluate(case) == case["expected"], case["id"]


def test_every_transition_has_an_allowed_control():
    cases = json.loads(FIXTURES.read_text())
    assert any(c["expected"]["verdict"] == "ALLOW" for c in cases)
    assert any(c["expected"]["verdict"] == "REFUSE" for c in cases)

