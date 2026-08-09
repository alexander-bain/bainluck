"""Validate the C175-C177 search-truth closure matrix and fixture links."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
ROOT=Path(__file__).parents[2]
FIXTURE=ROOT/"tests/evals/fixtures/search_truth_closure_contract.json"
SOURCES={
 "response":ROOT/"tests/evals/fixtures/search_response_truth_contract.json",
 "recovery":ROOT/"tests/evals/fixtures/search_recovery_state_contract.json",
 "observability":ROOT/"tests/evals/fixtures/search_observability_truth_contract.json",
}

def load_corpus(path:str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("schema_version")!="search-truth-closure/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    rows=p.get("cases")
    if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or any(not isinstance(v,str) or not v for v in ids): raise ValueError("CASE_ID_REQUIRED")
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    return p

def source_ids(paths:dict[str,Path]=SOURCES)->dict[str,set[str]]:
    return {name:{r["id"] for r in json.loads(path.read_text(encoding="utf-8"))["cases"]} for name,path in paths.items()}

def evaluate_case(row:dict[str,Any],available:dict[str,set[str]])->dict[str,Any]:
    refs=row["refs"]; missing=sorted(f"{kind}:{case}" for kind,case in refs.items() if case not in available.get(kind,set()))
    required=set(row["required_modules"]); tests=set(row["required_tests"])
    reasons=[]
    if missing: reasons.append("LOWER_LEVEL_FIXTURE_MISSING")
    if not required: reasons.append("IMPLEMENTATION_OWNER_MISSING")
    if not tests: reasons.append("BOUNDARY_TEST_MISSING")
    if row["state"]=="partial" and "availability_metadata" not in row["contracts"]: reasons.append("PARTIAL_UNLABELED")
    if row["state"] in {"partial","complete","empty"} and "analytics_authority" not in row["contracts"]: reasons.append("ANALYTICS_AUTHORITY_MISSING")
    if row["transition"] in {"retry","backspace","stale"} and "generation_ownership" not in row["contracts"]: reasons.append("GENERATION_OWNERSHIP_MISSING")
    return {"verdict":"ready" if not reasons else "refuse","reason_codes":sorted(reasons),"missing_refs":missing}

def evaluate_corpus(p:dict[str,Any],available:dict[str,set[str]]|None=None)->dict[str,Any]:
    available=available or source_ids(); details=[]
    for row in sorted(p["cases"],key=lambda r:r["id"]):
        actual=evaluate_case(row,available); details.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"schema_version":p["schema_version"],"total":len(details),"passed":sum(d["passed"] for d in details),"details":details}

def main()->int:
    pa=argparse.ArgumentParser(description=__doc__); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args()
    result=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["passed"]==result["total"] else 1
if __name__=="__main__": raise SystemExit(main())
