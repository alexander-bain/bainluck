"""Compose Manus retirement, browser evidence, jank, and filing contracts."""
from __future__ import annotations
import argparse,json
from pathlib import Path
ROOT=Path(__file__).parents[2]
FIXTURE=ROOT/"tests/evals/fixtures/browser_replacement_closure_contract.json"
SOURCES={k:ROOT/f"tests/evals/fixtures/{v}.json" for k,v in {
 "retirement":"manus_retirement_contract","evidence":"browser_audit_replacement_contract",
 "jank":"browser_product_jank_contract","filing":"browser_sweep_filing_contract"}.items()}
def load_corpus(path=FIXTURE):
 p=json.loads(Path(path).read_text()); rows=p.get("cases")
 if p.get("schema_version")!="browser-replacement-closure/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
 ids=[r.get("id") for r in rows]
 if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
 return p
def source_ids(): return {k:{x["id"] for x in json.loads(v.read_text())["cases"]} for k,v in SOURCES.items()}
def evaluate_case(row,available):
 missing=sorted(f"{k}:{v}" for k,v in row["refs"].items() if v not in available.get(k,set()))
 reasons=[]
 if missing: reasons.append("LOWER_LEVEL_FIXTURE_MISSING")
 if not row.get("owners"): reasons.append("OWNER_MISSING")
 if not row.get("gates"): reasons.append("GATE_MISSING")
 return {"verdict":"ready" if not reasons else "refuse","reason_codes":reasons,"missing_refs":missing}
def evaluate_corpus(p):
 a=source_ids(); d=[]
 for r in p["cases"]:
  actual=evaluate_case(r,a); d.append({"id":r["id"],"actual":actual,"expected":r["expected"],"passed":actual==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); x=pa.parse_args(); r=evaluate_corpus(load_corpus(x.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
