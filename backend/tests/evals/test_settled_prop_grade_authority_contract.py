import json
from pathlib import Path

from scripts.evals.settled_prop_grade_authority_contract import evaluate


FIXTURES = Path(__file__).parent / "fixtures" / "settled_prop_grade_authority_contract.json"


def cases():
    return json.loads(FIXTURES.read_text())["cases"]


def test_corpus_matches_oracle():
    for case in cases():
        assert evaluate(case) == case["expected"], case["id"]


def test_resolution_source_never_creates_a_verdict():
    for case in cases():
        if case["id"] in {"generic_source_default_false", "void_source"}:
            assert evaluate(case)["state"] == "WITHHOLD"


def test_zero_actual_is_real_but_not_a_verdict():
    case = next(case for case in cases() if case["id"] == "actual_zero_only")
    assert evaluate(case)["state"] == "ACTUAL_ONLY"


def test_entity_and_threshold_conflicts_fail_closed():
    by_id = {case["id"]: evaluate(case) for case in cases()}
    assert by_id["mixed_players_one_graded"]["state"] == "WITHHOLD"
    assert by_id["ladder_thresholds_disagree"]["state"] == "WITHHOLD"

