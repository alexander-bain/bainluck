import copy,json
from pathlib import Path
import pytest
from scripts.evals.curator_market_match_contract import evaluate_case,evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/curator_market_match_contract.json"
def case(i): return copy.deepcopy(next(x for x in load_corpus(F)["cases"] if x["id"]==i))
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]>=14 and r["passed"]==r["total"]
def test_wildcard_refused(): assert evaluate_case(case("percent-literal-unescaped"))["boost"]==0
def test_title_only_no_boost(): assert evaluate_case(case("title-only-high-score"))["verdict"]=="NO_MATCH"
def test_exact_id_boosts(): assert evaluate_case(case("source-item-id-exact"))["boost"]==20
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
