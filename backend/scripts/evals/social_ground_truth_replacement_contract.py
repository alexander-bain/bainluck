"""Provider-neutral contract for reviewed social ground-truth intake."""
from __future__ import annotations
import argparse,json
from pathlib import Path
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/social_ground_truth_replacement_contract.json"
def load_corpus(path=FIXTURE):
 p=json.loads(Path(path).read_text()); rows=p.get("cases")
 if p.get("schema_version")!="social-ground-truth-replacement/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
 ids=[x.get("id") for x in rows]
 if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
 return p
def evaluate_case(r):
 x=r["input"]; reasons=[]; action="hold"
 if x.get("provider_specific_dependency"): reasons.append("PROVIDER_COUPLING_REMAINS")
 if x.get("extractor_status") not in {None,"pending"}: reasons.append("EXTRACTOR_BYPASSES_REVIEW")
 if not x.get("source_url") or not x.get("captured_at") or not x.get("extractor_version"): reasons.append("PROVENANCE_INCOMPLETE")
 if x.get("malformed") or x.get("partial_failure"): reasons.append("EXTRACTION_INVALID")
 status=x.get("review_status")
 if not reasons and status=="accepted": action="import"
 elif status in {"rejected","pending","reviewed",None}: action="hold"
 if x.get("duplicate_replay") and action=="import": action="idempotent_noop"
 freshness="unknown"
 if x.get("imported_at") and x.get("max_age_hours") is not None:
  freshness="stale" if x.get("age_hours",0)>x["max_age_hours"] else "current"
 return {"action":action,"freshness":freshness,"reason_codes":sorted(reasons),"recall_generation_advances":action=="import" and freshness=="current"}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
