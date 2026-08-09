import copy,json
from pathlib import Path
import pytest
from scripts.evals.curator_generation_replacement_contract import evaluate_case,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/curator_generation_replacement_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]>=12 and r["passed"]==r["total"]
def test_rejection_revokes(): assert not evaluate_case(case("accepted-to-rejected"))["live"]
def test_partial_preserves_last_good(): assert evaluate_case(case("absent-from-partial-generation"))["live"]
def test_complete_retires_absent(): assert evaluate_case(case("absent-from-complete-generation"))["action"]=="retire_absent"
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
