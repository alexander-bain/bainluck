import json
from pathlib import Path

from backend.scripts.evals.morning_digest_discover_parity_contract import evaluate


FIXTURES = Path(__file__).parent / "fixtures" / "morning_digest_discover_parity_contract.json"


def test_corpus_matches_oracle():
    cases = json.loads(FIXTURES.read_text())
    assert len(cases) >= 15
    for case in cases:
        actual = evaluate(case)
        assert actual == case["expected"], case["id"]


def test_named_contract_dimensions_are_present():
    cases = json.loads(FIXTURES.read_text())
    reasons = {
        reason
        for case in cases
        for reason in case["expected"]["reason_codes"]
    }
    assert {
        "not_open",
        "stale",
        "completed_event",
        "quality_suppressed",
        "no_real_price",
        "locked_near_certain",
        "duplicate_family",
        "malformed_label",
        "candidate_unverified",
        "stale_digest_score",
        "not_in_current_discover",
    } <= reasons


def test_healthy_controls_are_allowed():
    cases = json.loads(FIXTURES.read_text())
    allowed = [case["id"] for case in cases if evaluate(case)["verdict"] == "ALLOW"]
    assert {"healthy_liquid_open_mover", "healthy_high_volume_extreme"} <= set(allowed)

