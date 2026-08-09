from __future__ import annotations
import copy,json
from pathlib import Path
import pytest
from scripts.evals.browser_audit_replacement_contract import evaluate_case,evaluate_corpus,load_corpus
FIXTURE=Path(__file__).parent/"fixtures/browser_audit_replacement_contract.json"
def _case(i:str)->dict:return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==i))
def test_corpus_covers_product_and_refusal_states()->None:
    result=evaluate_corpus(load_corpus(FIXTURE)); assert result["total"]>=20 and result["passed"]==result["total"]
    assert {r["expected"]["verdict"] for r in load_corpus(FIXTURE)["cases"]}=={"pass","fail","refuse"}
def test_issue_requires_durable_evidence()->None:
    assert evaluate_case(_case("failure-without-repro"))["verdict"]=="refuse"
def test_admin_refuses_without_credential_boundary()->None:
    assert "AUTH_BOUNDARY_UNAPPROVED" in evaluate_case(_case("admin-without-approved-auth-boundary"))["reason_codes"]
def test_latency_requires_timing_artifact()->None:
    row=_case("discover-first-card-under-three-seconds"); row["input"]["artifacts"].remove("duration_ms"); assert "TIMING_MISSING" in evaluate_case(row)["reason_codes"]
def test_loader_refuses_bad_version_and_duplicates(tmp_path:Path)->None:
    c=load_corpus(FIXTURE); c["schema_version"]="x"; p=tmp_path/"x.json"; p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):load_corpus(p)
    c=load_corpus(FIXTURE); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"):load_corpus(p)
