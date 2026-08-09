"""Classify browser-observable product jank without guessing market semantics."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/browser_product_jank_contract.json"

def load_corpus(path:str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("schema_version")!="browser-product-jank/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    rows=p.get("cases")
    if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or len(ids)!=len(set(ids)): raise ValueError("CASE_IDS_INVALID")
    return p

def classify(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]; kind=x["kind"]; reasons=[]; verdict="PASS"
    if kind=="lifecycle":
        if not x.get("event_time_authoritative") or x.get("status") is None: verdict="UNKNOWN"; reasons=["LIFECYCLE_AUTHORITY_MISSING"]
        elif x["status"] in {"resolved","hidden"}: verdict="PASS"
        elif x.get("event_in_past") and x["status"] in {"open","upcoming","live"}: verdict="FAIL"; reasons=["PAST_EVENT_ACTIVE"]
        elif x.get("deadline_in_past") and x.get("deadline_explicit"): verdict="FAIL"; reasons=["EXPIRED_RUNG_VISIBLE"]
    elif kind=="outcomes":
        if x.get("cross_market_identity_proved"): verdict="FAIL"; reasons=["CROSS_MARKET_OUTCOME"]
        elif x.get("authoritative_leader_id") and x.get("authoritative_leader_id") not in x.get("visible_ids",[]): verdict="FAIL"; reasons=["AUTHORITATIVE_LEADER_MISSING"]
        elif x.get("exclusive") is None or x.get("complete") is None: verdict="UNKNOWN"; reasons=["OUTCOME_SHAPE_UNKNOWN"]
        elif x.get("exclusive") and x.get("complete"):
            total=sum(x.get("probabilities",[])); tolerance=x.get("rounding_tolerance",0.02)
            if abs(total-1)>tolerance: verdict="FAIL"; reasons=["COMPLETE_EXCLUSIVE_SUM_INVALID"]
    elif kind=="ladder":
        if not x.get("operators_known") or not x.get("thresholds_parsed"): verdict="UNKNOWN"; reasons=["LADDER_SEMANTICS_UNKNOWN"]
        elif not x.get("sorted",True): verdict="FAIL"; reasons=["LADDER_ORDER_WRONG"]
        elif not x.get("monotonic",True): verdict="FAIL"; reasons=["LADDER_MONOTONICITY_BROKEN"]
    elif kind=="loading":
        if x.get("named_empty"): verdict="PASS"
        elif x.get("real_content"): verdict="PASS"
        elif x.get("elapsed_ms",0)>=x.get("stuck_after_ms",20000): verdict="FAIL"; reasons=["LOADING_STUCK"]
        else: verdict="UNKNOWN"; reasons=["LOADING_WINDOW_INCOMPLETE"]
    file_issue=verdict=="FAIL" and x.get("evidence_complete",False)
    return {"verdict":verdict,"reason_codes":sorted(reasons),"file_issue":file_issue,"fingerprint":f'{kind}:{reasons[0]}' if reasons else None}

def evaluate_corpus(p:dict[str,Any])->dict[str,Any]:
    d=[]
    for row in p["cases"]:
        actual=classify(row); d.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main()->int:
    pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
