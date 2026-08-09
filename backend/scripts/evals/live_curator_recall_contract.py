"""Truth contract for persisted external-curator rows consumed by Discover."""
from __future__ import annotations
import argparse,json
from pathlib import Path
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/live_curator_recall_contract.json"
def load_corpus(path=FIXTURE):
 p=json.loads(Path(path).read_text()); rows=p.get("cases")
 if p.get("schema_version")!="live-curator-recall/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
 ids=[x.get("id") for x in rows]
 if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
 return p
def evaluate_case(r):
 x=r["input"]; reasons=[]
 status=x.get("review_status")
 if status not in {"accepted","approved"}: reasons.append("NOT_EXPLICITLY_ACCEPTED")
 age=x.get("age_hours"); max_age=x.get("max_age_hours",168)
 if age is None: reasons.append("FRESHNESS_UNKNOWN")
 elif age<0: reasons.append("FUTURE_TIMESTAMP")
 elif age>max_age: reasons.append("EVIDENCE_STALE")
 if x.get("generation_complete") is False: reasons.append("GENERATION_PARTIAL")
 if x.get("revoked"): reasons.append("REVIEW_REVOKED")
 eligible=not reasons
 action="recall" if eligible else ("serve_stale_marked" if x.get("last_good") and "GENERATION_PARTIAL" in reasons else "exclude")
 if x.get("duplicate_replay") and eligible: action="idempotent_recall"
 return {"eligible":eligible,"action":action,"reason_codes":sorted(reasons)}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
