import copy
import json
from pathlib import Path

from scripts.evals.product_measurement_claim_gate import evaluate_claim


FIXTURES = Path(__file__).parent / "fixtures" / "product_measurement_claim_gate.json"


def pack():
    return json.loads(FIXTURES.read_text())


def materialize(case):
    evidence = copy.deepcopy(pack()["valid"][case["base"]])
    for dotted, value in case["set"].items():
        target = evidence
        parts = dotted.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    return evidence


def test_all_four_reference_claims_are_accepted():
    for domain, evidence in pack()["valid"].items():
        result = evaluate_claim(evidence)
        assert result["verdict"] == "ACCEPT_CLAIM", (domain, result)
        assert result["reasons"] == []


def test_every_adversary_is_refused_for_its_named_reason():
    for case in pack()["adversaries"]:
        result = evaluate_claim(materialize(case))
        assert result["verdict"] == "REFUSE_CLAIM", case["id"]
        assert case["reason"] in result["reasons"], (case["id"], result)


def test_fixture_reasons_are_unique_failure_classes():
    reasons = [case["reason"] for case in pack()["adversaries"]]
    assert len(set(reasons)) == len(reasons)


def test_unsupported_domain_fails_closed():
    evidence = copy.deepcopy(pack()["valid"]["latency"])
    evidence["domain"] = "vibes"
    assert "DOMAIN_UNSUPPORTED" in evaluate_claim(evidence)["reasons"]


def test_missing_common_envelope_fails_before_domain_logic():
    result = evaluate_claim({"domain": "latency"})
    assert result["verdict"] == "REFUSE_CLAIM"
    assert result["reasons"] == ["COMMON_FIELDS_MISSING"]


def test_latency_failures_must_count_in_attempts_and_percentiles():
    evidence = copy.deepcopy(pack()["valid"]["latency"])
    evidence["candidate"].update(attempts=40, successes=38, failures=2, failures_in_percentile=False)
    result = evaluate_claim(evidence)
    assert "LATENCY_CANDIDATE_FAILURES_CENSORED" in result["reasons"]


def test_population_bridge_allows_explicit_calibration_version_change():
    evidence = copy.deepcopy(pack()["valid"]["calibration"])
    evidence["candidate"].update(population_version="v4", population_count=650000, population_bridge_valid=True)
    result = evaluate_claim(evidence)
    assert "CALIBRATION_POPULATION_UNBRIDGED" not in result["reasons"]
    assert "CALIBRATION_POPULATION_DRIFT" not in result["reasons"]
