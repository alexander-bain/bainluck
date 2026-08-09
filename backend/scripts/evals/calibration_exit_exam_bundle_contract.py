"""Decision authority for CAL-P024 cohort exit-exam evidence bundles."""

from __future__ import annotations

from typing import Any


REQUIRED_METRICS = {"canonical_ece", "alternate_ece", "brier", "sparse_bins"}


def evaluate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    before = bundle.get("before")
    after = bundle.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {"verdict": "REFUSE", "reasons": ["COMPARISON_MISSING"]}

    missing = REQUIRED_METRICS - set(before) | REQUIRED_METRICS - set(after)
    if missing:
        reasons.add("ROBUSTNESS_METRICS_MISSING")
    for side in (before, after):
        if not isinstance(side.get("observations"), int) or side.get("observations", 0) < 1:
            reasons.add("OBSERVATION_COUNT_INVALID")
        if not isinstance(side.get("independent_questions"), int) or side.get("independent_questions", 0) < 1:
            reasons.add("INDEPENDENT_QUESTION_COUNT_INVALID")
        if not isinstance(side.get("sparse_bins"), int) or side.get("sparse_bins", -1) < 0:
            reasons.add("SPARSE_BIN_DISCLOSURE_INVALID")
    if before.get("population_hash") != after.get("population_hash"):
        reasons.add("POPULATION_CHANGED")
    if before.get("independent_questions") != after.get("independent_questions"):
        reasons.add("INDEPENDENT_POPULATION_CHANGED")

    consequential = bool(bundle.get("consequential_claim"))
    independent = after.get("independent_questions", 0)
    if consequential and not bundle.get("clustered_uncertainty"):
        reasons.add("CLUSTERED_UNCERTAINTY_MISSING")
    if consequential and (not isinstance(independent, int) or independent < 30):
        reasons.add("INDEPENDENT_SAMPLE_TOO_SMALL_FOR_INFERENCE")
    if not consequential and bundle.get("claimed_population_inference"):
        reasons.add("FORENSIC_EVIDENCE_OVERCLAIMED")

    canonical_delta = None
    alternate_delta = None
    brier_delta = None
    if not missing:
        try:
            canonical_delta = round(float(before["canonical_ece"]) - float(after["canonical_ece"]), 12)
            alternate_delta = round(float(before["alternate_ece"]) - float(after["alternate_ece"]), 12)
            brier_delta = round(float(before["brier"]) - float(after["brier"]), 12)
        except (KeyError, TypeError, ValueError):
            reasons.add("METRIC_VALUE_INVALID")

    floor = 0.005
    effect = "unavailable"
    if canonical_delta is not None:
        effect = "meaningful improvement" if canonical_delta >= floor else "no meaningful change"
        if bundle.get("effect_verdict") != effect:
            reasons.add("EFFECT_FLOOR_VERDICT_WRONG")
        if canonical_delta >= floor and alternate_delta is not None and alternate_delta <= 0:
            reasons.add("ALTERNATE_BINNING_CONTRADICTS")
        if canonical_delta >= floor and brier_delta is not None and brier_delta <= 0:
            reasons.add("BRIER_CONTRADICTS")

    return {
        "verdict": "ACCEPT" if not reasons else "REFUSE",
        "reasons": sorted(reasons),
        "effect": effect,
        "canonical_delta_pp": None if canonical_delta is None else round(canonical_delta * 100, 6),
        "alternate_delta_pp": None if alternate_delta is None else round(alternate_delta * 100, 6),
        "brier_delta": brier_delta,
    }


def evaluate_corpus(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": case["id"], **evaluate_bundle(case["bundle"])} for case in pack["cases"]]
