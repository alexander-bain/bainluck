"""Compose producer, serving, matching, and generation curator contracts."""
from __future__ import annotations
import argparse,json
from pathlib import Path
R=Path(__file__).parents[2]; F=R/"tests/evals/fixtures/curator_recall_closure_contract.json"
S={"producer":"social_ground_truth_replacement_contract","serving":"live_curator_recall_contract","match":"curator_market_match_contract","generation":"curator_generation_replacement_contract"}
def load_corpus(path=F):
 p=json.loads(Path(path).read_text()); c=p.get("cases")
 if p.get("schema_version")!="curator-recall-closure/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(c,list) or not c: raise ValueError("CASES_REQUIRED")
 return p
def ids(): return {k:{x["id"] for x in json.loads((R/f"tests/evals/fixtures/{v}.json").read_text())["cases"]} for k,v in S.items()}
def evaluate_case(r,a):
 missing=sorted(f"{k}:{v}" for k,v in r["refs"].items() if v not in a[k]); reasons=[]
 if missing: reasons.append("FIXTURE_MISSING")
 if not r.get("owners"): reasons.append("OWNER_MISSING")
 return {"verdict":"READY" if not reasons else "REFUSE","reason_codes":reasons,"missing_refs":missing}
def evaluate_corpus(p):
 a=ids(); d=[]
 for r in p["cases"]:
  x=evaluate_case(r,a); d.append({"id":r["id"],"actual":x,"expected":r["expected"],"passed":x==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(F)); z=pa.parse_args(); r=evaluate_corpus(load_corpus(z.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
