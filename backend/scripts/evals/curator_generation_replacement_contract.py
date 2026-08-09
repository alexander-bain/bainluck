"""Oracle for curator review revocation and atomic generation replacement."""
from __future__ import annotations
import argparse,json
from pathlib import Path
F=Path(__file__).parents[2]/"tests/evals/fixtures/curator_generation_replacement_contract.json"
def load_corpus(path=F):
 p=json.loads(Path(path).read_text()); c=p.get("cases")
 if p.get("schema_version")!="curator-generation-replacement/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(c,list) or not c: raise ValueError("CASES_REQUIRED")
 ids=[x.get("id") for x in c]
 if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
 return p
def evaluate_case(r):
 x=r["input"]; old=x.get("old_status"); new=x.get("new_status"); complete=x.get("generation_complete",True)
 if not complete: return {"action":"preserve_last_good","live":old in {"accepted","approved"},"reason":"generation_partial"}
 if new in {"rejected","pending"}: return {"action":"revoke","live":False,"reason":"review_changed"}
 if new in {"accepted","approved"}: return {"action":"upsert","live":True,"reason":"accepted"}
 if x.get("absent_from_generation"): return {"action":"retire_absent","live":False,"reason":"generation_replaced"}
 return {"action":"exclude","live":False,"reason":"decision_missing"}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(F)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
