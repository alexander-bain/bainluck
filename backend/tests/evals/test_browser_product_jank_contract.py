from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.browser_product_jank_contract import classify,evaluate_corpus,load_corpus
FIXTURE=Path(__file__).parent/"fixtures/browser_product_jank_contract.json"
def _case(i:str)->dict:return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==i))
def test_corpus_covers_verdicts_and_scoreboard_cases()->None:
    c=load_corpus(FIXTURE); r=evaluate_corpus(c); assert r["total"]>=23 and r["passed"]==r["total"]
    assert {x["expected"]["verdict"] for x in c["cases"]}=={"PASS","FAIL","UNKNOWN"}
def test_nonexclusive_sum_does_not_false_alarm()->None: assert classify(_case("independent-binaries-320pct"))["verdict"]=="PASS"
def test_title_date_without_authority_is_unknown()->None: assert classify(_case("date-from-title-only"))["verdict"]=="UNKNOWN"
def test_unknown_never_files()->None: assert not classify(_case("shape-not-in-dom"))["file_issue"]
def test_loader_refuses_bad_version_and_duplicates(tmp_path:Path)->None:
    c=load_corpus(FIXTURE); c["schema_version"]="x"; p=tmp_path/"x.json"; p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):load_corpus(p)
    c=load_corpus(FIXTURE); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_IDS_INVALID"):load_corpus(p)
