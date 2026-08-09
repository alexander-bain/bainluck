"""Residual oracle for integrated UX-P028 current-curator claims."""
from __future__ import annotations
import argparse,json
from pathlib import Path
F=Path(__file__).parents[2]/"tests/evals/fixtures/int023_curator_residual_contract.json"
def load_corpus(path=F):
 p=json.loads(Path(path).read_text()); c=p.get("cases")
 if p.get("schema_version")!="int023-curator-residual/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(c,list) or not c: raise ValueError("CASES_REQUIRED")
 return p
def evaluate_case(r):
 x=r["input"]; reasons=[]
 if x.get("status") not in {"accepted","approved"}: reasons.append("NOT_EXPLICITLY_ACCEPTED")
 if x.get("source_age_days",0)>x.get("max_age_days",14): reasons.append("SOURCE_EVIDENCE_STALE")
 if x.get("wildcard_unescaped"): reasons.append("WILDCARD_UNESCAPED")
 if not x.get("identity_confident",False): reasons.append("IDENTITY_UNPROVED")
 if x.get("revoked") and x.get("persisted_live"): reasons.append("REVOCATION_NOT_APPLIED")
 if x.get("generation_partial") and x.get("published"): reasons.append("PARTIAL_GENERATION_PUBLISHED")
 return {"verdict":"PASS" if not reasons else "REFUSE","reason_codes":sorted(reasons)}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(F)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
