"""Dependency-free oracle for authoritative search analytics."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/search_observability_truth_contract.json"

def load_corpus(path:str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("schema_version")!="search-observability-truth/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    rows=p.get("cases")
    if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or any(not isinstance(v,str) or not v for v in ids): raise ValueError("CASE_ID_REQUIRED")
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    return p

def evaluate_case(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]; owned=x.get("owned",True); state=x["state"]; attempt=x.get("attempt",1)
    complete=state in {"complete","authoritative_empty"}; partial=state=="degraded"
    log_intent=owned and state not in {"unavailable","cancelled"} and attempt==1
    count_authoritative=owned and complete
    no_result_eligible=count_authoritative and x.get("result_count",0)==0
    return {
        "log_intent":log_intent,
        "count_authoritative":count_authoritative,
        "logged_result_count":x.get("result_count") if count_authoritative else None,
        "degradation_dimension":sorted(x.get("degraded",[])) if owned and partial else [],
        "retry_linked":attempt>1,
        "no_result_eligible":no_result_eligible,
        "dedupe_key":x.get("intent_id") if owned else None,
    }

def evaluate_corpus(p:dict[str,Any])->dict[str,Any]:
    details=[]
    for row in sorted(p["cases"],key=lambda r:r["id"]):
        actual=evaluate_case(row); details.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"schema_version":p["schema_version"],"total":len(details),"passed":sum(d["passed"] for d in details),"details":details}

def main()->int:
    pa=argparse.ArgumentParser(description=__doc__); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args()
    result=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["passed"]==result["total"] else 1
if __name__=="__main__": raise SystemExit(main())
