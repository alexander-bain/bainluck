import json
from pathlib import Path

from scripts.evals.nonfutures_envelope_renderability_contract import evaluate


FIXTURES = Path(__file__).parent / "fixtures" / "nonfutures_envelope_renderability_contract.json"


def test_fixture_corpus_matches_oracle():
    cases = json.loads(FIXTURES.read_text())
    assert len(cases) >= 18
    for case in cases:
        assert evaluate(case) == case["expected"], case["id"]


def test_required_named_and_surface_cases_exist():
    cases = json.loads(FIXTURES.read_text())
    ids = {case["id"] for case in cases}
    assert {
        "tour_de_france_2026_result",
        "belgian_gp_live_empty",
        "backend_present_web_dropped",
        "backend_present_native_dropped",
        "poison_child_healthy_sibling",
        "honestly_withheld_empty_concept",
    } <= ids


def test_every_failure_has_a_typed_reason():
    cases = json.loads(FIXTURES.read_text())
    for case in cases:
        result = evaluate(case)
        if result["verdict"] == "FAIL":
            assert result["reason_codes"], case["id"]

