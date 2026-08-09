import json
from pathlib import Path

from scripts.evals.trading_activity_authority_contract import classify


FIXTURES = Path(__file__).parent / "fixtures" / "trading_activity_authority_contract.json"


def cases():
    return json.loads(FIXTURES.read_text())


def test_fixture_corpus_matches_ruling():
    for case in cases():
        assert classify(**case["input"]) == case["expected"], case["id"]


def test_sparse_null_volume_is_always_unknown():
    for moves in range(0, 20):
        result = classify(volume=None, snapshots=2, distinct_moves=moves, min_snapshots=5, min_moves=3)
        assert result["classification"] == "unknown"


def test_populated_volume_has_priority_over_movement():
    result = classify(volume=0, snapshots=100, distinct_moves=99, min_snapshots=5, min_moves=3)
    assert result == {"classification": "untraded", "provenance": "volume_proven"}


def test_every_result_carries_provenance():
    for case in cases():
        assert classify(**case["input"])["provenance"]
