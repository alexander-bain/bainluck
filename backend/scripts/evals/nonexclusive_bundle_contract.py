"""Pure C119 market exclusivity and calibration publication evaluator."""
from __future__ import annotations
import copy, json
from pathlib import Path
from typing import Any
FIXTURE = Path(__file__).parents[2]/"tests"/"evals"/"fixtures"/"nonexclusive_bundle_contract.json"

def _merge(a,b):
    out=copy.deepcopy(a)
    for k,v in b.items(): out[k]=_merge(out[k],v) if isinstance(v,dict) and isinstance(out.get(k),dict) else copy.deepcopy(v)
    return out
def load_corpus(path=FIXTURE):
    p=json.loads(Path(path).read_text());
    if p.get("schema_version")!="nonexclusive-bundle/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    ids=[x.get("id") for x in p["cases"]]
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    p["cases"]=[_merge(p["defaults"],x) for x in p["cases"]]; return p
def classify(r:dict[str,Any])->dict[str,Any]:
    e=r["evidence"]; reason=None; shape="unknown"; normalize=False; publish=False
    if e["duplicate_ids"] or e["contradictory"]: reason="conflicting_shape_evidence"
    elif e["outcome_count"]==1: shape="orphan"; reason="orphan_half_market"
    elif e["independent_binary_questions"] or e["winner_count"]>1: shape="independent_bundle"; reason="nonexclusive_bundle"
    elif e["parent_condition_missing"]: reason="parent_condition_unknown"
    elif e["exclusive_proved"] and e["outcome_count"]>=3 and e["winner_count"]==1:
        shape="mex_field"; publish=True; normalize=e["probability_sum"]>r["threshold"]+r["tolerance"]
    elif e["outcome_count"]==2 and not e["independent_binary_questions"]: shape="binary"; publish=True
    else: reason="shape_unknown"
    disposition="published" if publish else "excluded_unknown" if reason in {"conflicting_shape_evidence","parent_condition_unknown","shape_unknown"} else "excluded_structural"
    if r["cohort_after_n"] is not None: disposition="parked_below_publish_bar" if r["cohort_after_n"]<r["publish_bar"] else "published_cohort"
    return {"shape":shape,"normalize":normalize,"publish":publish,"reason":reason,"disposition":disposition}
def evaluate_corpus(p):
    d=[]
    for r in sorted(p["cases"],key=lambda x:x["id"]):
        a=classify(r); d.append({"id":r["id"],"passed":a==r["expected"],"actual":a,"expected":r["expected"]})
    return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
    r=evaluate_corpus(load_corpus()); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
