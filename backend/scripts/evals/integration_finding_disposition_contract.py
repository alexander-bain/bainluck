"""Contract for integrating code with an applicable blocking audit finding."""

from __future__ import annotations


def disposition(*, finding_severity: str, applies_to_head: bool, repaired: bool, explicitly_overruled: bool, overruling_authority: str | None, regression_test_wired: bool) -> dict[str, str]:
    if finding_severity not in {"P1", "P2"} or not applies_to_head:
        return {"verdict": "ALLOW", "reason": "nonblocking_or_inapplicable"}
    if repaired and regression_test_wired:
        return {"verdict": "ALLOW", "reason": "repaired_and_guarded"}
    if explicitly_overruled and overruling_authority in {"Alex", "program_owner"}:
        return {"verdict": "ALLOW_WITH_DEBT", "reason": "explicit_risk_acceptance"}
    if repaired and not regression_test_wired:
        return {"verdict": "REFUSE", "reason": "repair_unguarded"}
    return {"verdict": "REFUSE", "reason": "blocking_finding_unresolved"}
