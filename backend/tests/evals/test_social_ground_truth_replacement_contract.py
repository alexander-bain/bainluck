import copy,json
from pathlib import Path
import pytest
from scripts.evals.social_ground_truth_replacement_contract import evaluate_case,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/social_ground_truth_replacement_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]>=14 and r["passed"]==r["total"]
def test_reviewed_is_not_accepted(): assert evaluate_case(case("reviewed-not-accepted-holds"))["action"]=="hold"
def test_provider_coupling_refused(): assert "PROVIDER_COUPLING_REMAINS" in evaluate_case(case("manus-coupling-refused"))["reason_codes"]
def test_current_accept_advances(): assert evaluate_case(case("accepted-current-imports"))["recall_generation_advances"]
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
