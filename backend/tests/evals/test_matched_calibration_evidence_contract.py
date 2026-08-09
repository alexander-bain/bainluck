import json
from pathlib import Path

from scripts.evals.matched_calibration_evidence_contract import evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "matched_calibration_evidence_contract.json"


def cases():
    return json.loads(FIXTURE.read_text())["cases"]


def test_every_case_matches_the_oracle():
    for case in cases():
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_client_cannot_publish_the_finding():
    case = next(c for c in cases() if c["id"] == "client-selects-widest-gap")
    assert "CLIENT_ADJUDICATED_CALIBRATION" in evaluate(case["input"])["reasons"]


def test_consequential_claim_needs_independent_count():
    case = next(c for c in cases() if c["id"] == "outcomes-only-disclosure")
    assert "INDEPENDENT_COUNT_MISSING" in evaluate(case["input"])["reasons"]


def test_decile_matching_is_not_exact_mix_control():
    case = next(c for c in cases() if c["id"] == "broad-bin-called-fixed-mix")
    assert "MIX_CONTROL_OVERCLAIMED" in evaluate(case["input"])["reasons"]
