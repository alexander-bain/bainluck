"""Statistical authority for product metric claims.

The caller supplies estimates and uncertainty from the appropriate domain method
(cluster bootstrap, paired bootstrap, Wilson interval, etc.). This gate prevents
point estimates from being promoted to decisions without the design metadata that
makes those estimates meaningful.
"""

from __future__ import annotations

from typing import Any


def holm_rejections(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Holm step-down family-wise error control, returned in original order."""
    indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
    rejected = [False] * len(p_values)
    still_rejecting = True
    m = len(p_values)
    for rank, (index, p_value) in enumerate(indexed):
        threshold = alpha / (m - rank)
        if still_rejecting and p_value <= threshold:
            rejected[index] = True
        else:
            still_rejecting = False
    return rejected


def evaluate_statistical_claim(claim: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    required = {
        "analysis_id", "outcome", "independent_unit", "independent_units",
        "estimate", "ci_low", "ci_high", "practical_effect_floor",
        "direction", "analysis_plan_created_at", "data_window_started_at",
        "comparison_family", "p_values", "target_index", "uncertainty_method",
    }
    if required - set(claim):
        return {"verdict": "REFUSE", "reasons": ["STAT_FIELDS_MISSING"]}
    if not claim.get("independent_unit"):
        reasons.append("INDEPENDENT_UNIT_UNDECLARED")
    units = claim.get("independent_units")
    if not isinstance(units, int) or units < 30:
        reasons.append("INDEPENDENT_SAMPLE_TOO_SMALL")
    if claim.get("raw_rows", units) > max(units, 1) * 20 and not claim.get("clustered_uncertainty"):
        reasons.append("PSEUDOREPLICATION_UNCORRECTED")
    low, high, estimate = claim.get("ci_low"), claim.get("ci_high"), claim.get("estimate")
    if not all(isinstance(v, (int, float)) for v in (low, high, estimate)) or low > estimate or estimate > high:
        reasons.append("INVALID_UNCERTAINTY_INTERVAL")
    elif claim["direction"] == "increase":
        if low <= 0:
            reasons.append("INTERVAL_CROSSES_NULL")
        if low < claim["practical_effect_floor"]:
            reasons.append("PRACTICAL_EFFECT_NOT_ESTABLISHED")
    elif claim["direction"] == "decrease":
        if high >= 0:
            reasons.append("INTERVAL_CROSSES_NULL")
        if high > -claim["practical_effect_floor"]:
            reasons.append("PRACTICAL_EFFECT_NOT_ESTABLISHED")
    else:
        reasons.append("DIRECTION_INVALID")
    if not claim.get("uncertainty_method"):
        reasons.append("UNCERTAINTY_METHOD_UNDECLARED")
    if claim.get("analysis_plan_created_at") >= claim.get("data_window_started_at"):
        reasons.append("ANALYSIS_NOT_PROSPECTIVE")
    p_values = claim.get("p_values")
    target = claim.get("target_index")
    if not isinstance(p_values, list) or not p_values or not all(isinstance(p, (int, float)) and 0 <= p <= 1 for p in p_values):
        reasons.append("P_VALUES_INVALID")
    elif not isinstance(target, int) or not 0 <= target < len(p_values):
        reasons.append("TARGET_COMPARISON_INVALID")
    elif len(p_values) > 1 and not holm_rejections(p_values)[target]:
        reasons.append("MULTIPLE_COMPARISON_NOT_SIGNIFICANT")
    if len(p_values) != claim.get("comparison_family"):
        reasons.append("COMPARISON_FAMILY_INCOMPLETE")
    if claim.get("model_selected_on_same_data", False):
        reasons.append("MODEL_SELECTION_LEAKAGE")
    return {"verdict": "ACCEPT" if not reasons else "REFUSE", "reasons": sorted(set(reasons))}
