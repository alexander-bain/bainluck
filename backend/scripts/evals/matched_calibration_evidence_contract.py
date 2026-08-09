"""Canonical authority for matched-cohort calibration evidence.

Extends the calibration evidence domain with backend-decision ownership,
independence disclosure, common-support honesty, and input validity.
"""

from __future__ import annotations

from typing import Any


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    rows = case.get("rows") or []

    for row in rows:
        n = row.get("n")
        winners = row.get("winners")
        total_prob = row.get("sum_prob")
        bucket = row.get("bucket_idx")
        if not isinstance(bucket, int) or not 0 <= bucket <= 9:
            reasons.add("INVALID_BUCKET_INDEX")
        if not isinstance(n, (int, float)) or n <= 0:
            reasons.add("INVALID_SAMPLE_COUNT")
            continue
        if not isinstance(winners, (int, float)) or not 0 <= winners <= n:
            reasons.add("INVALID_WINNER_COUNT")
        if not isinstance(total_prob, (int, float)) or not 0 <= total_prob <= n:
            reasons.add("INVALID_PROBABILITY_SUM")

    if case.get("client_computed_metric") or case.get("client_selected_finding"):
        reasons.add("CLIENT_ADJUDICATED_CALIBRATION")
    if case.get("claim_rendered") and not case.get("backend_decision_present"):
        reasons.add("CLAIM_LACKS_BACKEND_AUTHORITY")
    if case.get("claim_rendered"):
        if not isinstance(case.get("outcome_n"), int) or case.get("outcome_n", 0) <= 0:
            reasons.add("OUTCOME_COUNT_MISSING")
        if not isinstance(case.get("independent_question_n"), int) or case.get("independent_question_n", 0) <= 0:
            reasons.add("INDEPENDENT_COUNT_MISSING")
    if case.get("claims_mix_fixed") and not case.get("exact_common_support"):
        reasons.add("MIX_CONTROL_OVERCLAIMED")
    if case.get("selected_extreme_from", 1) > 1 and not case.get("selection_disclosed"):
        reasons.add("EXTREME_SELECTION_UNDISCLOSED")

    return {
        "verdict": "ALLOW" if not reasons else "REFUSE",
        "reasons": sorted(reasons),
    }
