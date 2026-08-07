import json
from pathlib import Path

from scripts.evals.ux_stack_honesty_residual_contract import evaluate


FIXTURES = Path(__file__).parent / "fixtures" / "ux_stack_honesty_residual_contract.json"


def test_corpus_matches_oracle():
    cases = json.loads(FIXTURES.read_text())
    assert len(cases) >= 9
    for case in cases:
        assert evaluate(case) == case["expected"], case["id"]


def test_each_int011_residual_has_both_directions():
    cases = json.loads(FIXTURES.read_text())
    by_kind = {}
    for case in cases:
        by_kind.setdefault(case["kind"], set()).add(case["expected"]["verdict"])
    assert by_kind == {
        "phantom_parity": {"ALLOW", "REFUSE"},
        "active_point": {"ALLOW", "REFUSE"},
        "bar_geometry": {"ALLOW", "REFUSE"},
    }

