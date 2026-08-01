from __future__ import annotations
import copy
from pathlib import Path
import pytest
from scripts.evals.nonexclusive_bundle_contract import classify,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures"/"nonexclusive_bundle_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
    r=evaluate_corpus(load_corpus(F)); assert r["total"]==20 and r["passed"]==20
def test_category_never_changes_shape():
    base=case("cricket-multiwinner")
    verdicts=[]
    for c in ("cricket","esports","entertainment"):
        row=copy.deepcopy(base); row["category"]=c; verdicts.append(classify(row))
    assert verdicts[0]==verdicts[1]==verdicts[2]
@pytest.mark.parametrize("i",["poison-first","poison-middle","poison-last"])
def test_poison_bundle_is_contained(i): assert classify(case(i))["reason"]=="conflicting_shape_evidence"
def test_threshold_boundary():
    assert classify(case("mex-at-threshold"))["normalize"] is False
    assert classify(case("mex-above-threshold"))["normalize"] is True
def test_independent_one_winner_still_not_mex(): assert classify(case("independent-one-winner"))["shape"]=="independent_bundle"
def test_cricket_below_bar_parks(): assert classify(case("cricket-corrected-below-bar"))["disposition"]=="parked_below_publish_bar"
def test_order_independent():
    p=load_corpus(F); q=copy.deepcopy(p); q["cases"].reverse(); assert evaluate_corpus(p)==evaluate_corpus(q)
