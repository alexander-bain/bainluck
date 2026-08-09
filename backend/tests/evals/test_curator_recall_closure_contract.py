import copy,json
from pathlib import Path
import pytest
from scripts.evals.curator_recall_closure_contract import evaluate_case,evaluate_corpus,ids,load_corpus
F=Path(__file__).parent/"fixtures/curator_recall_closure_contract.json"
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]==10 and r["passed"]==10
def test_all_refs_resolve(): assert all(not x["actual"]["missing_refs"] for x in evaluate_corpus(load_corpus(F))["details"])
def test_matrix_complete(): assert set(load_corpus(F)["implementation_matrix"])=={"contract","extractor","review","persistence","serving","matching","health"}
def test_missing_ref_refuses():
 r=copy.deepcopy(load_corpus(F)["cases"][0]); r["refs"]["match"]="x"; assert evaluate_case(r,ids())["verdict"]=="REFUSE"
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
