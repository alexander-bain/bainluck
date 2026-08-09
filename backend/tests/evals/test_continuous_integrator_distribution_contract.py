import json
from pathlib import Path

from backend.scripts.evals.continuous_integrator_distribution_contract import verdict


FIXTURES = Path(__file__).parent / "fixtures" / "continuous_integrator_distribution_contract.json"


def test_fixture_corpus_matches_distribution_oracle():
    for case in json.loads(FIXTURES.read_text()):
        assert verdict(**case["input"]) == case["expected"], case["id"]


def test_acceptance_requires_every_distribution_layer():
    keys = ("ruling_tracked", "command_tracked", "ci_marker", "local_command_matches")
    for missing in keys:
        state = {key: True for key in keys}
        state[missing] = False
        assert verdict(**state)["verdict"] == "REFUSE", missing


def test_complete_distribution_accepts():
    assert verdict(ruling_tracked=True, command_tracked=True, ci_marker=True, local_command_matches=True) == {"verdict": "ACCEPT", "reason": "distributed_and_guarded"}
