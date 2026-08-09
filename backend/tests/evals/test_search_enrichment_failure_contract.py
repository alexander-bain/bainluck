import json
from pathlib import Path

from scripts.evals.search_enrichment_failure_contract import OPTIONAL_STAGES, outcome


FIXTURES = Path(__file__).parent / "fixtures" / "search_enrichment_failure_contract.json"


def test_fixture_corpus_matches_oracle():
    for case in json.loads(FIXTURES.read_text()):
        assert outcome(**case["input"]) == case["expected"], case["id"]


def test_every_optional_stage_degrades_on_query_timeout():
    for stage in OPTIONAL_STAGES:
        result = outcome(stage=stage, failure="query_timeout", has_base_results=True)
        assert result == {"http": 200, "base_results": True, "degraded": [stage]}


def test_non_timeout_failures_never_hide_as_degradation():
    for stage in OPTIONAL_STAGES:
        result = outcome(stage=stage, failure="integrity_error", has_base_results=True)
        assert result["http"] == 500
        assert result["degraded"] == []


def test_base_results_survive_optional_enrichment_timeout():
    result = outcome(stage="event_odds", failure="query_timeout", has_base_results=True)
    assert result["base_results"] is True
