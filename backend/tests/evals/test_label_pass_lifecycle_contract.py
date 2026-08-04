from scripts.evals.label_pass_lifecycle_contract import load_corpus, evaluate_corpus, pending_decision, post_decision

def case(i): return next(r for r in load_corpus()["cases"] if r["id"]==i)
def test_corpus():
    r=evaluate_corpus(load_corpus()); assert r["total"]==23; assert r["passed"]==23, r
def test_stale_never_writes():
    for i in ("resolved","past-resolution","missing-market","overtaken","unmatched-email","get-valid-post-stale"):
        assert post_decision(case(i))["writes"]==0
def test_prose_is_not_retirement_authority(): assert pending_decision(case("title-llm-only"))[0]=="quarantine"
def test_valid_semantics_preserved():
    assert post_decision(case("valid-accept"))["delta"]==8
    assert post_decision(case("valid-reject"))["delta"]==-18
    assert post_decision(case("valid-kill-switch-off"))["delta"]==0
def test_skip_stale_is_not_training(): assert post_decision(case("stale-skip"))["writes"]==0
