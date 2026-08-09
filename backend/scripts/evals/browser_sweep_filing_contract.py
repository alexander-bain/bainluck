"""Pure state machine for browser-sweep issue filing and recovery."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from typing import Any
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/browser_sweep_filing_contract.json"
SAFE=re.compile(r"^[a-z0-9._:/-]{1,240}$")
def load_corpus(path:str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text()); rows=p.get("cases")
    if p.get("schema_version")!="browser-sweep-filing/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in rows];
    if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
    return p
def evaluate_case(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]; verdict=x["verdict"]; reasons=[]
    if not x.get("manifest_valid",False): reasons.append("MANIFEST_UNTRUSTED")
    if not x.get("sha_bound",False): reasons.append("SHA_UNBOUND")
    fp=x.get("fingerprint","")
    if fp and not SAFE.fullmatch(fp): reasons.append("FINGERPRINT_UNSAFE")
    if x.get("artifact_expired",False): reasons.append("ARTIFACT_UNAVAILABLE")
    action="no_op"
    if reasons: action="refuse"
    elif verdict in {"UNKNOWN","INFRA"}: action="no_op"
    elif verdict=="FAIL": action="comment" if x.get("open_issue") else ("comment" if x.get("concurrent_claim_lost") else "file")
    elif verdict=="PASS":
        if x.get("open_issue") and x.get("consecutive_clean",0)>=2: action="comment_close"
        elif x.get("open_issue"): action="comment_recovery_pending"
    return {"action":action,"reason_codes":sorted(reasons),"new_episode":verdict=="FAIL" and x.get("closed_prior",False) and not reasons}
def evaluate_corpus(p):
    d=[]
    for r in p["cases"]:
        a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
    return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main()->int:
    pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
