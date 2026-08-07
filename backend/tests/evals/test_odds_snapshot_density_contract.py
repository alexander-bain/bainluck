from scripts.evals.odds_snapshot_density_contract import decide,evaluate,load,recovery
def case(i): return next(c for c in load()["cases"] if c["id"]==i)
def test_corpus():
 r=evaluate(load()); assert r["total"]==19; assert r["passed"]==r["total"],r
def test_rows_are_not_observation_density():
 assert decide(case("ten-bookmakers-one-instant"))["verdict"]=="red"
 assert decide(case("healthy-unchanged"))["verdict"]=="green"
def test_never_covered_differs_from_stopped():
 assert decide(case("never-covered"))["verdict"]=="unknown"
 assert decide(case("capture-stopped"))["verdict"]=="red"
def test_recovery_requires_history():
 assert recovery(case("history-recoverable"))["verdict"]=="recoverable"
 assert recovery(case("history-ambiguous"))["verdict"]=="refuse"
