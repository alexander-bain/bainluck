"""Dependency-free search recovery transition oracle."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/search_recovery_state_contract.json"

def load_corpus(path: str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("schema_version")!="search-recovery-state/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    c=p.get("cases")
    if not isinstance(c,list) or not c: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in c if isinstance(r,dict)]
    if len(ids)!=len(c) or any(not isinstance(v,str) or not v for v in ids): raise ValueError("CASE_ID_REQUIRED")
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    return p

def evaluate_case(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]; transition=x["transition"]; prior=x.get("prior_rows",0); incoming=x.get("incoming_rows",0)
    owned=x.get("owned",True); partial=x.get("partial",False); error=x.get("error",False)
    rows=prior; warning=False; retry=False; loading=False; err=False; cache="preserve"; terminal="idle"; analytics=0
    reasons=[]
    if transition in {"clear","unmount","new_query"}:
        rows=0 if transition=="clear" else prior; terminal="cancelled"; reasons.append("GENERATION_INVALIDATED")
    elif not owned:
        terminal="stale_refused"; reasons.append("STALE_GENERATION")
    elif error:
        err=True; retry=True; terminal="failed"; reasons.append("RETRYABLE_FAILURE")
    elif partial:
        rows=prior if prior else incoming; warning=True; retry=True; terminal="partial"; reasons.append("PARTIAL_PRESERVED" if prior else "PARTIAL_COLD")
    else:
        rows=incoming; cache="promote"; terminal="complete"; analytics=incoming
        if transition=="retry_complete": reasons.append("RECOVERED")
    return {"rendered_rows":rows,"warning":warning,"error":err,"loading":loading,"retry":retry,"cache_action":cache,"analytics_count":analytics,"terminal":terminal,"reason_codes":sorted(reasons)}

def evaluate_corpus(p:dict[str,Any])->dict[str,Any]:
    d=[]
    for r in sorted(p["cases"],key=lambda x:x["id"]):
        a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
    return {"schema_version":p["schema_version"],"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}

def main()->int:
    pa=argparse.ArgumentParser(description=__doc__); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
