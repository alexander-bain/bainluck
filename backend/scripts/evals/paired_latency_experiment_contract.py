"""Dependency-free authority for paired production latency experiments."""

from __future__ import annotations

import math
from statistics import median
from typing import Any


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct * len(ordered)))
    return ordered[rank - 1]


def evaluate_pairs(pairs: list[dict[str, Any]], *, timeout_ms: float = 30_000, min_pairs: int = 20, max_control_drift_pct: float = 25.0) -> dict[str, Any]:
    reasons: list[str] = []
    if len(pairs) < min_pairs:
        reasons.append("PAIR_SAMPLE_TOO_SMALL")
    baseline_values: list[float] = []
    candidate_values: list[float] = []
    control_values: list[float] = []
    deltas: list[float] = []
    orders: list[str] = []
    for pair in pairs:
        if pair.get("request_shape_baseline") != pair.get("request_shape_candidate"):
            reasons.append("REQUEST_SHAPE_MISMATCH")
        if pair.get("cache_state_baseline") != pair.get("cache_state_candidate"):
            reasons.append("CACHE_STATE_MISMATCH")
        order = pair.get("order")
        if order not in {"baseline_first", "candidate_first"}:
            reasons.append("ORDER_UNDECLARED")
        else:
            orders.append(order)
        baseline = timeout_ms if pair.get("baseline_failed") else pair.get("baseline_ms")
        candidate = timeout_ms if pair.get("candidate_failed") else pair.get("candidate_ms")
        control = pair.get("control_ms")
        if not isinstance(baseline, (int, float)) or not isinstance(candidate, (int, float)):
            reasons.append("LATENCY_VALUE_MISSING")
            continue
        baseline_values.append(float(baseline))
        candidate_values.append(float(candidate))
        deltas.append(float(candidate) - float(baseline))
        if isinstance(control, (int, float)):
            control_values.append(float(control))
        else:
            reasons.append("CONTROL_MISSING")
    if orders and ("baseline_first" not in orders or "candidate_first" not in orders):
        reasons.append("ORDER_NOT_INTERLEAVED")
    control_drift_pct = None
    if len(control_values) >= 4:
        midpoint = len(control_values) // 2
        early = median(control_values[:midpoint])
        late = median(control_values[midpoint:])
        control_drift_pct = abs(late - early) * 100 / max(1.0, early)
        if control_drift_pct > max_control_drift_pct:
            reasons.append("CONTROL_DRIFT_EXCESSIVE")
    else:
        reasons.append("CONTROL_SAMPLE_TOO_SMALL")
    return {
        "verdict": "COMPARE" if not reasons else "REFUSE",
        "reasons": sorted(set(reasons)),
        "pairs": len(pairs),
        "baseline_p95_ms": percentile(baseline_values, 0.95),
        "candidate_p95_ms": percentile(candidate_values, 0.95),
        "median_pair_delta_ms": median(deltas) if deltas else None,
        "candidate_faster_pairs": sum(delta < 0 for delta in deltas),
        "control_drift_pct": control_drift_pct,
        "failures_counted_as_ms": timeout_ms,
    }
