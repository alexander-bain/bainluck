import json
from pathlib import Path

from scripts.evals.measurement_surface_truth_contract import evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "measurement_surface_truth_contract.json"


def cases():
    return json.loads(FIXTURE.read_text())["cases"]


def test_every_case_matches_the_oracle():
    for case in cases():
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_deadline_omission_cannot_publish_green():
    case = next(c for c in cases() if c["id"] == "deadline-skips-final-league")
    assert "RUN_COMPLETENESS_HIDDEN" in evaluate(case["input"])["reasons"]


def test_closed_rows_cannot_vouch_for_open_freshness():
    case = next(c for c in cases() if c["id"] == "closed-market-masks-stale-open")
    assert "CLOSED_MARKET_MASKED_OPEN_FRESHNESS" in evaluate(case["input"])["reasons"]


def test_cross_source_coverage_is_a_union():
    case = next(c for c in cases() if c["id"] == "disjoint-source-coverage")
    assert "COVERAGE_UNION_UNDERCOUNTED" in evaluate(case["input"])["reasons"]
