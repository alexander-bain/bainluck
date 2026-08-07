from scripts.evals.playoff_grid_native_parity_contract import decide,evaluate,load,parity
def case(i): return next(c for c in load()["cases"] if c["id"]==i)
def test_corpus():
 r=evaluate(load()); assert r["total"]==15; assert r["passed"]==r["total"],r
def test_live_probability_and_real_zero_survive():
 assert decide(case("live-make-playoffs"))["verdict"]=="probability"
 assert decide(case("real-zero-live"))["verdict"]=="probability"
def test_settled_is_graded_not_blank():
 assert decide(case("clinched-grade"))["verdict"]=="grade"
 assert decide(case("eliminated-grade"))["verdict"]=="grade"
def test_native_state_loss_is_drift():
 assert parity(case("clinched-state-lost-native"))["verdict"]=="drifted"
