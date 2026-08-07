"""Oracle for INT-011 cross-surface honesty residuals."""

from __future__ import annotations


def evaluate(case: dict) -> dict:
    kind = case["kind"]
    reasons: list[str] = []

    if kind == "phantom_parity":
        decisions = case.get("surface_decisions", {})
        if len(set(decisions.values())) > 1:
            reasons.append("surface_filter_drift")
        if case.get("fabricated") and any(v == "KEEP" for v in decisions.values()):
            reasons.append("fabricated_price_survives")

    elif kind == "active_point":
        if case.get("series_value") is None and case.get("callback_emitted"):
            reasons.append("null_signal_emits_probability")
        if case.get("series_value") is None and case.get("emitted_probability") == 0.5:
            reasons.append("null_signal_becomes_even")

    elif kind == "bar_geometry":
        printed = int(round(float(case.get("probability", 0)) * 100))
        width = int(case.get("width_pct", 0))
        if printed != width:
            reasons.append("label_fill_mismatch")

    else:
        reasons.append("unknown_kind")

    return {"verdict": "REFUSE" if reasons else "ALLOW", "reason_codes": reasons}

