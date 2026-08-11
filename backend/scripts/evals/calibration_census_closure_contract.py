"""Extends calibration_population_integrity: implementation-ready C253 closure."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/"tests/evals/fixtures/calibration_census_closure_contract.json"
def load_pack(path=FIXTURE): return json.loads(Path(path).read_text())
def evaluate(case):
 windows=case.get("windows",[]); reasons=[]
 if not windows or not windows[-1].get("exhausted"): reasons.append("TAIL_NOT_EXHAUSTED")
 prior=None; watermark=None
 for i,w in enumerate(windows):
  if i==0 and w.get("cursor_in")!=case.get("start_cursor",0): reasons.append("START_CURSOR_MISMATCH")
  if prior is not None and w.get("cursor_in")!=prior: reasons.append("CURSOR_CHAIN_BROKEN")
  bounds=w.get("window")
  if bounds:
   if bounds["lo"]<=w["cursor_in"] or bounds["hi"]<bounds["lo"]: reasons.append("WINDOW_BOUNDS_INVALID")
  prior=w.get("next_offset")
  wm=w.get("source_watermark")
  if watermark is None: watermark=wm
  elif wm!=watermark: reasons.append("SOURCE_WATERMARK_DRIFT")
 if watermark is None: reasons.append("SOURCE_WATERMARK_ABSENT")
 complete=not any(r in reasons for r in ("TAIL_NOT_EXHAUSTED","START_CURSOR_MISMATCH","CURSOR_CHAIN_BROKEN","WINDOW_BOUNDS_INVALID"))
 evidence="snapshot" if complete and watermark is not None and "SOURCE_WATERMARK_DRIFT" not in reasons else "rolling" if complete else "partial"
 chronology=case.get("chronology")
 timing="unknown" if not chronology or chronology.get("settlement_at") is None or chronology.get("final_quote_at") is None else "contaminated" if chronology["final_quote_at"]>=chronology["settlement_at"] else "pre_settlement"
 return {"process_exit":0 if complete else 1,"walk_evidence":evidence,"timing_verdict":timing,"reason_codes":sorted(set(reasons))}
def evaluate_pack(pack):
 rows=[]
 for c in pack["cases"]:
  a=evaluate(c); rows.append({"id":c["id"],"actual":a,"passed":a==c["expected"]})
 return {"total":len(rows),"passed":sum(r["passed"] for r in rows),"rows":rows}
