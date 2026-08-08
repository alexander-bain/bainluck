"""Oracle for search/typeahead degraded response and client preservation semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/search_degraded_response_contract.json"


def load_corpus(path: str|Path=FIXTURE)->dict[str,Any]:
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version")!="search-degraded-response/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    cases=payload.get("cases")
    if not isinstance(cases,list) or not cases: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in cases if isinstance(r,dict)]
    if len(ids)!=len(cases) or any(not isinstance(v,str) or not v for v in ids): raise ValueError("CASE_ID_REQUIRED")
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]
    response=x["response"]
    prior=x.get("prior",False)
    has_items=x.get("has_items",False)
    stale=x.get("stale_available",False)
    reasons:list[str]=[]
    if response=="complete":
        metadata="complete"; client="replace"; display="results" if has_items else "no_match"; cache="write"
    elif response=="authoritative_empty":
        metadata="complete"; client="replace"; display="no_match"; cache="write"
    elif response=="partial":
        metadata="degraded"; client="preserve" if prior else "accept_partial"; display="kept_results" if prior else "partial"; cache="refuse"
        reasons.append("RESPONSE_PARTIAL")
    elif response=="unavailable":
        metadata="unavailable"; client="preserve" if prior else "refuse"; display="kept_results" if prior else "retry"; cache="refuse"
        reasons.append("RESPONSE_UNAVAILABLE")
    elif response=="malformed":
        metadata="invalid"; client="preserve" if prior else "refuse"; display="kept_results" if prior else "retry"; cache="refuse"
        reasons.append("SCHEMA_INVALID")
    elif response=="stale":
        metadata="stale"; client="accept_stale"; display="stale_results"; cache="serve_stale"
        reasons.append("DATED_STALE")
    else: raise ValueError(f"RESPONSE_INVALID:{response}")
    if x.get("retry") and response=="complete": reasons.append("RECOVERED")
    return {"response_metadata":metadata,"client_action":client,"display_state":display,"cache_action":cache,"retry_available":response not in {"complete","authoritative_empty"},"reason_codes":sorted(reasons)}


def evaluate_corpus(payload:dict[str,Any])->dict[str,Any]:
    details=[]
    for row in sorted(payload["cases"],key=lambda x:x["id"]):
        actual=evaluate_case(row); details.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"schema_version":payload["schema_version"],"total":len(details),"passed":sum(x["passed"] for x in details),"details":details}


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--fixture",default=str(FIXTURE)); args=parser.parse_args()
    report=evaluate_corpus(load_corpus(args.fixture)); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if report["passed"]==report["total"] else 1


if __name__=="__main__": raise SystemExit(main())
