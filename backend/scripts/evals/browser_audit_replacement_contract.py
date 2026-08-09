"""Dependency-free oracle for the vendor-neutral rendered-site audit."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/browser_audit_replacement_contract.json"

def load_corpus(path:str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("schema_version")!="browser-audit-replacement/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    rows=p.get("cases")
    if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or any(not isinstance(v,str) or not v for v in ids): raise ValueError("CASE_ID_REQUIRED")
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    return p

def evaluate_case(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]; observed=x.get("observed",False); named=x.get("named",False); artifacts=x.get("artifacts",[])
    auth=x.get("auth",False); credential_boundary=x.get("credential_boundary",False); expected=x.get("expected_state","pass")
    reasons=[]
    if auth and not credential_boundary: reasons.append("AUTH_BOUNDARY_UNAPPROVED")
    if not observed: reasons.append("OBSERVATION_MISSING")
    if expected!="pass" and not named: reasons.append("FAILURE_UNNAMED")
    required={"screenshot","url","timestamp","frontend_sha"}
    if not required.issubset(set(artifacts)): reasons.append("EVIDENCE_INCOMPLETE")
    if x.get("latency",False) and "duration_ms" not in artifacts: reasons.append("TIMING_MISSING")
    if x.get("network",False) and "request_ledger" not in artifacts: reasons.append("NETWORK_EVIDENCE_MISSING")
    if x.get("issue_candidate",False) and not {"fingerprint","repro_steps"}.issubset(set(artifacts)): reasons.append("FILING_EVIDENCE_MISSING")
    return {"verdict":"refuse" if reasons else expected,"reason_codes":sorted(reasons),"file_issue":x.get("issue_candidate",False) and not reasons and expected=="fail"}

def evaluate_corpus(p:dict[str,Any])->dict[str,Any]:
    details=[]
    for row in sorted(p["cases"],key=lambda r:r["id"]):
        actual=evaluate_case(row); details.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"schema_version":p["schema_version"],"total":len(details),"passed":sum(d["passed"] for d in details),"details":details}

def main()->int:
    pa=argparse.ArgumentParser(description=__doc__); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args()
    result=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["passed"]==result["total"] else 1
if __name__=="__main__": raise SystemExit(main())
