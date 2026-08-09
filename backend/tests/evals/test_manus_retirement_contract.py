from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.manus_retirement_contract import evaluate_case,evaluate_corpus,load_corpus
FIXTURE=Path(__file__).parent/"fixtures/manus_retirement_contract.json"
def _case(i:str)->dict:return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==i))
def test_corpus_covers_dispositions()->None:
    result=evaluate_corpus(load_corpus(FIXTURE)); assert result["total"]>=18 and result["passed"]==result["total"]
    assert {r["expected"]["action"] for r in load_corpus(FIXTURE)["cases"]}>={"delete","annotate","retain"}
def test_dead_executable_is_deleted()->None:
    assert evaluate_case(_case("required-red-workflow"))["action"]=="delete"
def test_historical_evidence_retained_with_notice()->None:
    v=evaluate_case(_case("historical-audit-files")); assert v["action"]=="retain" and v["notice_required"]
def test_replacement_path_is_explicit()->None:
    assert evaluate_case(_case("replacement-grid-sentinel"))["reproduction_path"]=="replacement"
def test_loader_refuses_bad_version_and_duplicates(tmp_path:Path)->None:
    c=load_corpus(FIXTURE); c["schema_version"]="x"; p=tmp_path/"x.json"; p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):load_corpus(p)
    c=load_corpus(FIXTURE); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"):load_corpus(p)
