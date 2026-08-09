import json

from scripts.evals.event_cache_repair_closure_contract import DEFAULT_FIXTURES, evaluate, evaluate_pack


def test_all_cache_lifecycle_cases_match_the_closure_oracle() -> None:
    result = evaluate_pack(json.loads(DEFAULT_FIXTURES.read_text()))
    assert result["passed"] == result["cases"] == 12


def test_both_live_failure_shapes_obey_last_good_authority() -> None:
    repaired = {"stale": True, "none_reads_stale": True,
                "negative_rechecks_positive_and_stale": True}
    assert evaluate({**repaired, "build": "none"})["response"] == "stale"
    assert evaluate({**repaired, "build": "exception"})["response"] == "stale"


def test_both_concurrent_write_orders_are_safe() -> None:
    negative_then_success = evaluate({
        "build": "success", "concurrent_negative_before_success": True,
        "success_clears_negative": True,
    })
    success_then_negative = evaluate({
        "build": "none", "concurrent_positive_before_negative": True,
        "negative_rechecks_positive_and_stale": True,
    })
    assert negative_then_success["verdict"] == "accept"
    assert success_then_negative["verdict"] == "accept"


def test_current_candidate_fails_none_and_reverse_race_contracts() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {row["id"]: evaluate(row["input"]) for row in pack["cases"]}
    assert rows["none-must-serve-last-good"]["verdict"] == "refuse"
    assert rows["success-then-negative-current-race"]["verdict"] == "refuse"
