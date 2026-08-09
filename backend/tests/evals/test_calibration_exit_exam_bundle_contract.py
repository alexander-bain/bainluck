import json
from pathlib import Path

from scripts.evals.calibration_exit_exam_bundle_contract import evaluate_bundle, evaluate_corpus


FIXTURE = Path(__file__).parent / "fixtures" / "calibration_exit_exam_bundle_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        result = evaluate_bundle(case["bundle"])
        assert result["verdict"] == case["expected"]["verdict"], case["id"]
        assert result["reasons"] == case["expected"]["reasons"], case["id"]


def test_exact_half_point_boundary_is_meaningful():
    case = next(row for row in pack()["cases"] if row["id"] == "exact-floor")
    result = evaluate_bundle(case["bundle"])
    assert result["canonical_delta_pp"] == 0.5
    assert result["effect"] == "meaningful improvement"


def test_forensic_small_n_is_allowed_without_population_claim():
    case = next(row for row in pack()["cases"] if row["id"] == "small-cricket-forensic")
    assert evaluate_bundle(case["bundle"])["verdict"] == "ACCEPT"


def test_corpus_covers_every_cal_p024_rider():
    results = evaluate_corpus(pack())
    reasons = {reason for result in results for reason in result["reasons"]}
    assert {
        "INDEPENDENT_QUESTION_COUNT_INVALID",
        "CLUSTERED_UNCERTAINTY_MISSING",
        "INDEPENDENT_SAMPLE_TOO_SMALL_FOR_INFERENCE",
        "ROBUSTNESS_METRICS_MISSING",
        "EFFECT_FLOOR_VERDICT_WRONG",
        "ALTERNATE_BINNING_CONTRADICTS",
        "BRIER_CONTRADICTS",
        "POPULATION_CHANGED",
        "FORENSIC_EVIDENCE_OVERCLAIMED",
    } <= reasons
