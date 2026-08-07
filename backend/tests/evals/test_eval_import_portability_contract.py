import json
from pathlib import Path

from scripts.evals.eval_import_portability_contract import evaluate, evaluate_suite


FIXTURES = Path(__file__).parent / "fixtures" / "eval_import_portability_contract.json"


def test_cases_match_oracle():
    corpus = json.loads(FIXTURES.read_text())
    assert len(corpus["cases"]) >= 14
    for case in corpus["cases"]:
        assert evaluate(case) == case["expected"], case["id"]


def test_suites_match_oracle():
    corpus = json.loads(FIXTURES.read_text())
    for suite in corpus["suites"]:
        assert evaluate_suite(suite["rows"]) == suite["expected"], suite["id"]


def test_c156_through_c159_are_explicitly_covered():
    corpus = json.loads(FIXTURES.read_text())
    ids = {case["id"] for case in corpus["cases"]}
    assert {"c156", "c157", "c158", "c159"} <= ids


