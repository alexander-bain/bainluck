"""Oracle for safe curator-evidence to market matching and boost eligibility."""
from __future__ import annotations
import argparse,json
from pathlib import Path
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/curator_market_match_contract.json"
def load_corpus(path=FIXTURE):
 p=json.loads(Path(path).read_text()); rows=p.get("cases")
 if p.get("schema_version")!="curator-market-match/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
 ids=[x.get("id") for x in rows]
 if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
 return p
def evaluate_case(r):
 x=r["input"]; reasons=[]
 if x.get("raw_wildcard_interpolated"): reasons.append("WILDCARD_UNESCAPED")
 confidence=x.get("confidence",0)
 threshold=x.get("threshold",0.9)
 identity=x.get("item_id_match") or (x.get("entity_match") and x.get("title_match"))
 if not identity: reasons.append("IDENTITY_UNPROVED")
 if confidence<threshold: reasons.append("MATCH_CONFIDENCE_LOW")
 if x.get("cross_entity"): reasons.append("ENTITY_COLLISION")
 candidates=x.get("candidate_ids",[])
 if len(candidates)!=len(set(candidates)): reasons.append("DUPLICATE_CANDIDATE")
 eligible=not reasons
 return {"verdict":"BOOST" if eligible else ("NO_MATCH" if "IDENTITY_UNPROVED" in reasons else "REFUSE"),"boost":20 if eligible else 0,"reason_codes":sorted(reasons)}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
