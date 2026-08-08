from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.search_degraded_response_contract import evaluate_case,evaluate_corpus,load_corpus

FIXTURE=Path(__file__).parent/"fixtures/search_degraded_response_contract.json"
def _case(case_id:str)->dict: return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==case_id))

def test_corpus_covers_web_native_and_both_endpoints()->None:
    corpus=load_corpus(FIXTURE); report=evaluate_corpus(corpus)
    assert report["total"]>=20 and report["passed"]==report["total"]
    assert {r["surface"] for r in corpus["cases"]}=={"web","native"}
    assert {r["endpoint"] for r in corpus["cases"]}=={"search","typeahead"}

def test_degraded_refresh_preserves_prior()->None:
    verdict=evaluate_case(_case("web-typeahead-prior-partial"))
    assert verdict["client_action"]=="preserve" and verdict["cache_action"]=="refuse"

def test_degraded_cold_result_is_partial_not_no_match()->None:
    verdict=evaluate_case(_case("native-search-cold-partial-empty"))
    assert verdict["display_state"]=="partial"

def test_authoritative_empty_can_show_no_match()->None:
    verdict=evaluate_case(_case("web-search-authoritative-empty"))
    assert verdict["display_state"]=="no_match" and verdict["retry_available"] is False

def test_loader_rejects_bad_version_and_duplicate_ids(tmp_path:Path)->None:
    corpus=load_corpus(FIXTURE); corpus["schema_version"]="wrong"; path=tmp_path/"bad.json"; path.write_text(json.dumps(corpus),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(path)
    corpus=load_corpus(FIXTURE); corpus["cases"].append(copy.deepcopy(corpus["cases"][0])); path.write_text(json.dumps(corpus),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"): load_corpus(path)
