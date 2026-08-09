"""Authority contract for promoting decisions into PRODUCT-BRAIN rulings."""

from __future__ import annotations


def verdict(*, decision_state: str, attributed_to_alex: bool, ci_guarded: bool) -> dict[str, str]:
    if decision_state == "explicit_approval" and attributed_to_alex:
        return {"verdict": "ACCEPT", "reason": "explicit_authority"}
    if decision_state in {"open", "inferred", "ambiguous"}:
        return {"verdict": "REFUSE", "reason": "needs_alex_ruling"}
    if ci_guarded and not attributed_to_alex:
        return {"verdict": "REFUSE", "reason": "guarded_without_authority"}
    return {"verdict": "HOLD", "reason": "not_a_standing_ruling"}
