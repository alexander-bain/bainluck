import copy,json
from pathlib import Path
import pytest
from scripts.evals.live_curator_recall_contract import evaluate_case,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/live_curator_recall_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]>=14 and r["passed"]==r["total"]
def test_reviewed_excluded(): assert not evaluate_case(case("reviewed-excluded"))["eligible"]
def test_frozen_excluded(): assert "EVIDENCE_STALE" in evaluate_case(case("accepted-stale-excluded"))["reason_codes"]
def test_partial_last_good_marked(): assert evaluate_case(case("partial-preserves-marked-last-good"))["action"]=="serve_stale_marked"
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
