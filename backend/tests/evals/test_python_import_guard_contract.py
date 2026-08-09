import json

from scripts.evals.python_import_guard_contract import DEFAULT_FIXTURES, evaluate, evaluate_pack


def test_all_import_shapes_match_the_ast_oracle() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    result = evaluate_pack(pack)
    assert result["passed"] == result["cases"] == 17


def test_current_regex_has_both_false_negatives_and_false_positives() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {case["id"]: evaluate(case) for case in pack["cases"]}
    assert rows["from-exact-backend"]["verdict"] == "REFUSE"
    assert rows["from-exact-backend"]["current_regex_flags"] is False
    assert rows["docstring-is-not-import"]["verdict"] == "ALLOW"
    assert rows["docstring-is-not-import"]["current_regex_flags"] is True


def test_dynamic_literal_import_cannot_bypass_the_guard() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {case["id"]: evaluate(case) for case in pack["cases"]}
    assert rows["literal-importlib"]["forbidden"] == ["dynamic:backend.scripts.evals.foo"]
    assert rows["import-module-alias"]["forbidden"] == ["dynamic:backend.app.main"]
