from __future__ import annotations
import copy
from pathlib import Path
import pytest
from scripts.evals.nonexclusive_bundle_contract import classify,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures"/"nonexclusive_bundle_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
    r=evaluate_corpus(load_corpus(F)); assert r["total"]==20 and r["passed"]==20
def test_category_never_changes_shape_but_scope_changes_publication():
    """CAL-P045(c): cricket JOINED the excluded scope; the invariant is unchanged.

    Shape stays category-independent — that is the part that must never move.
    What moved is membership: cricket was diagnosed (exam item 3, verdict
    `exclusion`) and now sits with esports, while entertainment stays
    measured_only because its structural rival is evidenced but its timing rival
    is UNKNOWN and unobtainable without new capture. Entertainment is the control
    here, and it is deliberately still in this test.
    """
    base=case("cricket-multiwinner")
    verdicts={}
    for c in ("cricket","esports","entertainment"):
        row=copy.deepcopy(base); row["category"]=c; verdicts[c]=classify(row)
    assert {row["shape"] for row in verdicts.values()} == {"independent_bundle"}
    assert verdicts["cricket"]["disposition"] == "excluded_structural"
    assert verdicts["esports"]["disposition"] == "excluded_structural"
    assert verdicts["entertainment"]["disposition"] == "measured_only"
@pytest.mark.parametrize("i",["poison-first","poison-middle","poison-last"])
def test_poison_bundle_is_contained(i): assert classify(case(i))["reason"]=="conflicting_shape_evidence"
def test_threshold_boundary():
    assert classify(case("mex-at-threshold"))["normalize"] is False
    assert classify(case("mex-above-threshold"))["normalize"] is True
def test_independent_one_winner_still_not_mex(): assert classify(case("independent-one-winner"))["shape"]=="independent_bundle"
def test_cricket_below_bar_parks(): assert classify(case("cricket-corrected-below-bar"))["disposition"]=="parked_below_publish_bar"
def test_hockey_and_tennis_counterclasses_remain_measured():
    for i in ("hockey-multiwinner-counterclass", "tennis-multiwinner-counterclass"):
        assert classify(case(i))["disposition"] == "measured_only"
        assert classify(case(i))["publish"] is True

def test_real_production_predicates_and_sql_match_contract():
    from app.tasks import precompute_calibration as production

    from scripts.evals.nonexclusive_bundle_contract import EXCLUDED_CATEGORIES

    # ONE decision, two consumers. Two lists that agree today are how they drift.
    assert tuple(production.MULTI_BUNDLE_EXCLUDED_CATEGORIES) == EXCLUDED_CATEGORIES

    assert production.market_is_nonexclusive_bundle(3, 2) is True
    assert production.market_is_multi_bundle_excluded("esports", 3, 2) is True
    assert production.market_is_multi_bundle_excluded("cricket", 3, 2) is True
    # The counter-classes: same shape, well calibrated, still published. A
    # blanket exclusion would delete 81% of hockey and 47% of tennis.
    assert production.market_is_multi_bundle_excluded("hockey", 3, 2) is False
    assert production.market_is_multi_bundle_excluded("tennis", 3, 2) is False
    # Structurally gated, not category-gated: a 1-winner cricket bundle is still
    # published, exactly as the contract's classifier now says.
    assert production.market_is_multi_bundle_excluded("cricket", 3, 1) is False
    population_ctes = production._calibration_population_ctes()
    assert "NOT ro.is_nonexclusive_bundle" not in population_ctes
    assert "NOT ro.is_esports_bundle" in population_ctes
def test_order_independent():
    p=load_corpus(F); q=copy.deepcopy(p); q["cases"].reverse(); assert evaluate_corpus(p)==evaluate_corpus(q)
