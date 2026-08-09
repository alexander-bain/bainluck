from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.search_truth_closure_contract import evaluate_case,evaluate_corpus,load_corpus,source_ids
FIXTURE=Path(__file__).parent/"fixtures/search_truth_closure_contract.json"
def _case(i:str)->dict:return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==i))
def test_all_closure_cases_and_refs_are_ready()->None:
    result=evaluate_corpus(load_corpus(FIXTURE)); assert result["total"]>=12 and result["passed"]==result["total"]
def test_matrix_covers_full_stack()->None:
    matrix=load_corpus(FIXTURE)["implementation_matrix"]; assert set(matrix)=={"backend_response","backend_persistence","web","native"}
def test_missing_lower_level_reference_refuses()->None:
    row=_case("warm-partial-web"); row["refs"]["response"]="absent"; actual=evaluate_case(row,source_ids()); assert actual["verdict"]=="refuse" and "LOWER_LEVEL_FIXTURE_MISSING" in actual["reason_codes"]
def test_partial_without_availability_refuses()->None:
    row=_case("cold-partial-web"); row["contracts"].remove("availability_metadata"); assert "PARTIAL_UNLABELED" in evaluate_case(row,source_ids())["reason_codes"]
def test_loader_refuses_bad_version_and_duplicates(tmp_path:Path)->None:
    c=load_corpus(FIXTURE); c["schema_version"]="x"; p=tmp_path/"x.json"; p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):load_corpus(p)
    c=load_corpus(FIXTURE); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"):load_corpus(p)
