import json
from pathlib import Path

from scripts.evals.additional_markets_authority_contract import evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "additional_markets_authority_contract.json"


def cases():
    return json.loads(FIXTURE.read_text())["cases"]


def test_every_case_matches_the_oracle():
    for case in cases():
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_absence_never_becomes_zero():
    case = next(c for c in cases() if c["id"] == "missing-probability-becomes-zero")
    assert "MISSING_PROBABILITY_FABRICATED" in evaluate(case["input"])["reasons"]


def test_settled_rows_require_result_authority():
    case = next(c for c in cases() if c["id"] == "settled-event-still-quotes-price")
    assert "SETTLED_ROW_RENDERED_AS_LIVE_PRICE" in evaluate(case["input"])["reasons"]


def test_badge_counts_distinct_sources():
    case = next(c for c in cases() if c["id"] == "same-provider-triplicate")
    assert "SOURCE_BADGE_COUNTS_ROWS_NOT_SOURCES" in evaluate(case["input"])["reasons"]
