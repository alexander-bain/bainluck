from copy import deepcopy

from scripts.evals.task_health_truth_contract import evaluate, evaluate_pack, load_pack


def _case(case_id: str):
    pack = load_pack()
    return pack, deepcopy(next(row for row in pack["cases"] if row["id"] == case_id))


def test_versioned_corpus_matches_all_declared_results() -> None:
    pack = load_pack()
    result = evaluate_pack(pack)
    assert pack["policy"]["contract_version"] == "task-health-truth/v1"
    assert result["passed"] == result["cases"] == 18
    assert not [row for row in result["results"] if row["expected_mismatches"]]


def test_one_success_does_not_erase_five_recent_failures() -> None:
    pack, case = _case("five_failures_then_success")
    result = evaluate(case, pack["policy"])
    assert result["last_terminal_state"] == "complete_success"
    assert result["consecutive_failures"] == 0
    assert result["rolling"]["failures"] == 5
    assert result["rolling"]["failure_ratio"] == 0.833333
    assert result["health"] == "critical"


def test_evicted_history_is_unknown_not_zero_or_healthy() -> None:
    pack, case = _case("history_evicted")
    result = evaluate(case, pack["policy"])
    assert result["completeness"] == "unknown"
    assert result["health"] == "unknown"
    assert result["reasons"] == ["HISTORY_INCOMPLETE"]


def test_partial_return_is_never_counted_as_success() -> None:
    pack, case = _case("partial_budget_return")
    result = evaluate(case, pack["policy"])
    assert result["rolling"] == {
        "successes": 0, "failures": 0, "partials": 1, "terminal": 0,
        "failure_ratio": None, "boundary": "(evaluation_at-window, evaluation_at]",
    }
    assert result["health"] == "degraded"


def test_exact_24_hour_lower_boundary_is_excluded() -> None:
    pack, case = _case("exact_24h_boundary_excluded")
    result = evaluate(case, pack["policy"])
    assert result["rolling"]["failures"] == 0
    assert result["rolling"]["successes"] == 1


def test_clean_event_order_and_timezone_spelling_do_not_change_result() -> None:
    pack, case = _case("healthy_hourly")
    first = evaluate(case, pack["policy"])
    case["events"].reverse()
    case["events"][0]["at"] = "2026-08-01T04:00:00-07:00"
    assert evaluate(case, pack["policy"]) == first


def test_duplicate_poison_nonfinite_and_malformed_rows_contain_to_unknown() -> None:
    pack, duplicate = _case("duplicate_event")
    candidates = [duplicate]
    nonfinite = deepcopy(duplicate); nonfinite["events"] = [deepcopy(nonfinite["events"][0])]; nonfinite["events"][0]["duration_ms"] = float("inf"); candidates.append(nonfinite)
    missing = deepcopy(duplicate); missing["events"] = [{"event_id": "missing"}]; candidates.append(missing)
    wrong_shape = deepcopy(duplicate); wrong_shape["events"] = {}; candidates.append(wrong_shape)
    for case in candidates:
        assert evaluate(case, pack["policy"])["health"] == "unknown"


def test_schedule_change_recomputes_freshness_without_rewriting_history() -> None:
    pack, case = _case("healthy_six_hour_sparse")
    assert evaluate(case, pack["policy"])["health"] == "healthy"
    case["schedule"] = {"interval_hours": 1, "freshness_hours": 2}
    result = evaluate(case, pack["policy"])
    assert result["health"] == "critical"
    assert result["reasons"] == ["STALE_LAST_TERMINAL"]


def test_long_running_overlap_is_explicitly_unknown() -> None:
    pack, case = _case("healthy_hourly")
    case["events"][0]["duration_ms"] = 7_200_000
    case["events"][1]["duration_ms"] = 7_200_000
    result = evaluate(case, pack["policy"])
    assert result["health"] == "unknown"
    assert result["reasons"] == ["OVERLAPPING_RUNS"]


def test_repeated_evaluation_is_deterministic() -> None:
    pack, case = _case("failure_after_success")
    assert evaluate(case, pack["policy"]) == evaluate(deepcopy(case), deepcopy(pack["policy"]))


def test_zero_denominator_stays_none() -> None:
    pack, case = _case("never_run")
    result = evaluate(case, pack["policy"])
    assert result["rolling"]["terminal"] == 0
    assert result["rolling"]["failure_ratio"] is None
