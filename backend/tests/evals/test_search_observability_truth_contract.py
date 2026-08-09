from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.search_observability_truth_contract import evaluate_case,evaluate_corpus,load_corpus
FIXTURE=Path(__file__).parent/"fixtures/search_observability_truth_contract.json"
def _case(i:str)->dict:return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==i))
def test_corpus_covers_surfaces_endpoints_and_states()->None:
    c=load_corpus(FIXTURE); r=evaluate_corpus(c); assert r["total"]>=18 and r["passed"]==r["total"]
    assert {x["surface"] for x in c["cases"]}=={"backend","web","native"}; assert {x["endpoint"] for x in c["cases"]}=={"search","typeahead"}
def test_degraded_zero_is_not_no_result()->None:
    v=evaluate_case(_case("backend-futures-timeout-zero")); assert v["logged_result_count"] is None and not v["no_result_eligible"]
def test_authoritative_empty_is_a_real_miss()->None:
    v=evaluate_case(_case("backend-authoritative-empty")); assert v["logged_result_count"]==0 and v["no_result_eligible"]
def test_retry_links_without_double_counting_intent()->None:
    v=evaluate_case(_case("web-retry-complete")); assert v["retry_linked"] and not v["log_intent"] and v["count_authoritative"]
def test_loader_refuses_bad_version_and_duplicates(tmp_path:Path)->None:
    c=load_corpus(FIXTURE); c["schema_version"]="x"; p=tmp_path/"x.json"; p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):load_corpus(p)
    c=load_corpus(FIXTURE); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"):load_corpus(p)
