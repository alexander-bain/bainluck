from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.search_recovery_state_contract import evaluate_case,evaluate_corpus,load_corpus
FIXTURE=Path(__file__).parent/"fixtures/search_recovery_state_contract.json"
def _case(i:str)->dict:return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==i))
def test_corpus_covers_clients_endpoints_and_transitions()->None:
    c=load_corpus(FIXTURE); r=evaluate_corpus(c); assert r["total"]>=20 and r["passed"]==r["total"]
    assert {x["surface"] for x in c["cases"]}=={"web","native"}; assert {x["endpoint"] for x in c["cases"]}=={"search","typeahead"}
def test_partial_preserves_prior()->None:
    v=evaluate_case(_case("web-search-complete-to-partial")); assert v["rendered_rows"]==5 and v["warning"] and v["retry"]
def test_recovery_clears_warning_and_promotes_cache()->None:
    v=evaluate_case(_case("native-typeahead-retry-complete")); assert not v["warning"] and v["terminal"]=="complete" and v["cache_action"]=="promote"
def test_backspace_invalidates_generation()->None:
    v=evaluate_case(_case("native-search-backspace-clear")); assert v["terminal"]=="cancelled" and "GENERATION_INVALIDATED" in v["reason_codes"]
def test_loader_rejects_bad_version_and_duplicates(tmp_path:Path)->None:
    c=load_corpus(FIXTURE); c["schema_version"]="x"; p=tmp_path/"x.json"; p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):load_corpus(p)
    c=load_corpus(FIXTURE); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"):load_corpus(p)
