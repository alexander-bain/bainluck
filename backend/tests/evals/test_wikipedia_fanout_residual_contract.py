import json
from pathlib import Path

from backend.scripts.evals.wikipedia_fanout_residual_contract import admitted_requests


FIXTURES = Path(__file__).parent / "fixtures" / "wikipedia_fanout_residual_contract.json"


def _outcomes(spec):
    if isinstance(spec, list):
        return spec
    return [spec["repeat"]] * spec["count"]


def test_every_fixture_matches_admission_oracle():
    for case in json.loads(FIXTURES.read_text()):
        assert admitted_requests(_outcomes(case["outcomes"]), case["threshold"]) == case["expected_admitted"], case["id"]


def test_large_prequeued_burst_is_bounded_by_failure_threshold():
    assert admitted_requests(["throw"] * 10_000, threshold=5) == 5


def test_success_resets_consecutive_failure_count():
    sequence = (["throw"] * 4 + ["success"]) * 100
    assert admitted_requests(sequence, threshold=5) == len(sequence)


def test_healthy_not_found_resets_consecutive_failure_count():
    sequence = (["throw"] * 4 + ["not_found"]) * 100
    assert admitted_requests(sequence, threshold=5) == len(sequence)
