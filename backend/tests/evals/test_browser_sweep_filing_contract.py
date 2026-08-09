import copy,json
from pathlib import Path
import pytest
from scripts.evals.browser_sweep_filing_contract import evaluate_case,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/browser_sweep_filing_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
    r=evaluate_corpus(load_corpus(F)); assert r["total"]>=16 and r["passed"]==r["total"]
def test_unknown_never_files(): assert evaluate_case(case("unknown-noop"))["action"]=="no_op"
def test_two_clean_runs_close(): assert evaluate_case(case("second-clean-closes"))["action"]=="comment_close"
def test_injection_refused(): assert evaluate_case(case("injection-fingerprint"))["action"]=="refuse"
def test_loader(tmp_path):
    c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
    c=load_corpus(F); c["cases"].append(copy.deepcopy(c["cases"][0])); p.write_text(json.dumps(c))
    with pytest.raises(ValueError,match="CASE_IDS_INVALID"): load_corpus(p)
