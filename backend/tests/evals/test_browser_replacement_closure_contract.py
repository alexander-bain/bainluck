import copy,json
from pathlib import Path
import pytest
from scripts.evals.browser_replacement_closure_contract import evaluate_case,evaluate_corpus,load_corpus,source_ids
F=Path(__file__).parent/"fixtures/browser_replacement_closure_contract.json"
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]==8 and r["passed"]==8
def test_matrix_owns_all_layers(): assert set(load_corpus(F)["implementation_matrix"])=={"retire","runner","filer","tests"}
def test_missing_reference_refuses():
 row=copy.deepcopy(load_corpus(F)["cases"][0]); row["refs"]["jank"]="missing"; assert evaluate_case(row,source_ids())["verdict"]=="refuse"
def test_all_references_resolve(): assert all(not x["actual"]["missing_refs"] for x in evaluate_corpus(load_corpus(F))["details"])
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
