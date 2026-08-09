"""Residual contract for INT-022 UX-P024/P025/P026 integration."""
from __future__ import annotations
import argparse,json
from pathlib import Path
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/int022_ux_residual_contract.json"
def load_corpus(path=FIXTURE):
 p=json.loads(Path(path).read_text()); rows=p.get("cases")
 if p.get("schema_version")!="int022-ux-residual/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
 ids=[x.get("id") for x in rows]
 if len(ids)!=len(set(ids)) or any(not x for x in ids): raise ValueError("CASE_IDS_INVALID")
 return p
def evaluate_case(r):
 x=r["input"]; claim=x["claim"]; reasons=[]
 if claim=="ordering":
  if x.get("marquee_in_progress") and x.get("game_prepended_after_marquee"): reasons.append("MARQUEE_TOP_SLOT_DISPLACED")
  if x.get("items_dropped") or x.get("scores_changed"): reasons.append("REORDER_NOT_PURE")
 elif claim=="freshness":
  if x.get("fresh_candidate") and x.get("stale_candidate") and x.get("winner")!="fresh": reasons.append("STALE_WINS_OVER_FRESH")
  if x.get("all_stale") and not x.get("winner"): reasons.append("ALL_STALE_BLANKED")
 elif claim=="retirement":
  if x.get("dead_required_workflow_present"): reasons.append("DEAD_SWEEP_REMAINS")
  if x.get("health_reads_dead_manifest"): reasons.append("DEAD_HEALTH_REMAINS")
  if x.get("historical_deleted"): reasons.append("HISTORICAL_EVIDENCE_DELETED")
 return {"verdict":"FAIL" if reasons else "PASS","reason_codes":sorted(reasons)}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
