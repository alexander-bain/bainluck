"""Dependency-free oracle for playoff-grid qualification parity."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
FIXTURES=Path(__file__).resolve().parents[2]/"tests/evals/fixtures/playoff_grid_native_parity_contract.json"

def decide(c:dict[str,Any])->dict[str,str]:
    if not c.get("team_identity_valid",True) or not c.get("season_valid",True):
        return {"verdict":"refuse","reason":"identity_or_season_invalid"}
    if c.get("duplicate_sources_conflict"):
        return {"verdict":"refuse","reason":"source_conflict"}
    state=c.get("state")
    probability=c.get("probability")
    if state in {"clinched","eliminated"}:
        return {"verdict":"grade","reason":state}
    if state=="missing" or (state is None and probability is None):
        return {"verdict":"withhold","reason":"qualification_unknown"}
    if isinstance(probability,bool) or not isinstance(probability,(int,float)) or not 0<=probability<=1:
        return {"verdict":"refuse","reason":"invalid_probability"}
    return {"verdict":"probability","reason":"live_qualification"}

def parity(c:dict[str,Any])->dict[str,str]:
    backend=decide(c["backend"]); native=decide(c["native"])
    return {"verdict":"shared" if backend==native else "drifted","reason":"same_semantics" if backend==native else "native_loses_backend_state"}
def load(): return json.loads(FIXTURES.read_text())
def evaluate(p):
 rows=[]
 for c in p["cases"]:
  a=parity(c) if c["kind"]=="parity" else decide(c)
  rows.append({"id":c["id"],"passed":a==c["expected"],"actual":a})
 return {"total":len(rows),"passed":sum(r["passed"] for r in rows),"cases":rows}
if __name__=="__main__": print(json.dumps(evaluate(load()),indent=2,sort_keys=True))
