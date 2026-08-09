import json

from scripts.evals.chunked_coverage_recomposition_contract import DEFAULT_FIXTURES, evaluate, evaluate_pack


def test_all_recomposition_cases_match_the_oracle() -> None:
    result = evaluate_pack(json.loads(DEFAULT_FIXTURES.read_text()))
    assert result["passed"] == result["cases"] == 12


def test_partial_measurement_never_becomes_a_global_total() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {row["id"]: evaluate(row["input"]) for row in pack["cases"]}
    assert rows["one-missing-column-stays-unknown"]["totals"]["coverage_total"] is None
    assert rows["one-null-column-stays-unknown"]["totals"]["coverage_total"] is None
    assert rows["global-cannot-rescue-unknown-chunk"]["totals"]["coverage_total"] is None


def test_empty_curve_does_not_discard_valid_population_census() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "empty-curve-retains-measured-census")
    result = evaluate(case["input"])
    assert result["verdict"] == "publish_empty_curve_with_census"
    assert result["totals"] == {"plotted": 0, "coverage_total": 35}


def test_global_rung_is_added_once_not_per_chunk() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    case = next(row for row in pack["cases"] if row["id"] == "global-rung-added-once")
    assert evaluate(case["input"])["totals"]["unavailable"] == 5
