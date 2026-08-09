import json
from pathlib import Path

from scripts.evals.concept_terminal_residual_contract import verdict


FIXTURES = Path(__file__).parent / "fixtures" / "concept_terminal_residual_contract.json"


def cases():
    return json.loads(FIXTURES.read_text())


def test_every_fixture_matches_oracle():
    for case in cases():
        assert verdict(case["input"]) == case["expected"], case["id"]


def test_corpus_covers_definitive_and_temporary_failures():
    states = {case["expected"]["state"] for case in cases()}
    assert states == {"ready", "loading", "not_found", "unavailable"}


def test_only_404_is_definitive_absence_when_an_error_exists():
    for status in (400, 401, 403, 408, 429, 500, 502, 503, 504):
        result = verdict(
            {"has_error": True, "error_status": status, "retries_exhausted": True}
        )
        assert result["state"] == "unavailable", status


def test_data_always_wins():
    for status in (404, 429, 500, None):
        result = verdict(
            {
                "has_data": True,
                "has_error": True,
                "error_status": status,
                "retries_exhausted": True,
                "ceiling_reached": True,
            }
        )
        assert result == {"state": "ready", "reason": "data_wins"}
