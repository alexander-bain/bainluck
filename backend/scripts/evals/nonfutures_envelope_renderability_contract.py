"""Dependency-free oracle for non-futures Discover envelope renderability."""

from __future__ import annotations


TERMINAL = {"resolved", "closed", "settled", "final", "finalized", "completed"}


def _row_probabilities(rows: list[dict]) -> tuple[list[float], list[str]]:
    probs: list[float] = []
    reasons: list[str] = []
    for row in rows:
        value = row.get("probability")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            reasons.append("invalid_probability")
            continue
        value = float(value)
        if value < 0 or value > 1:
            reasons.append("invalid_probability_scale")
            continue
        probs.append(value)
    return probs, reasons


def _content(case: dict) -> tuple[bool, list[str]]:
    if case.get("authoritative_result"):
        return True, []

    card_type = case.get("type")
    if card_type == "bundle":
        child_results = [_content(child) for child in case.get("children", [])]
        if any(ok for ok, _ in child_results):
            if any(not ok for ok, _ in child_results) and not case.get(
                "poison_children_removed", False
            ):
                return False, ["unsanitized_child"]
            return True, []
        return False, ["no_renderable_child"]

    rows = case.get("rows", [])
    probs, reasons = _row_probabilities(rows)
    positive = [p for p in probs if p > 0]
    if not rows:
        reasons.append("empty_envelope")
    elif not probs:
        reasons.append("no_probability")
    elif not positive:
        reasons.append("zero_only")

    if positive and case.get("leader_required", True):
        names = {str(row.get("name") or "") for row in rows}
        leader = str(case.get("leader_name") or "")
        if not leader or leader not in names:
            reasons.append("leader_missing")

    return not reasons, list(dict.fromkeys(reasons))


def evaluate(case: dict) -> dict:
    content_ok, reasons = _content(case)
    backend_should_publish = content_ok

    web_ok = content_ok and case.get("web_decodes", True)
    native_ok = content_ok and case.get("native_decodes", True)
    if content_ok and not case.get("web_decodes", True):
        reasons.append("web_drops_payload")
    if content_ok and not case.get("native_decodes", True):
        reasons.append("native_drops_payload")

    actual_publish = bool(case.get("backend_publishes"))
    if actual_publish and not backend_should_publish:
        reasons.append("backend_publishes_empty")
    if not actual_publish and backend_should_publish:
        reasons.append("backend_withholds_valid")

    contract_ok = (
        actual_publish == backend_should_publish
        and (not actual_publish or (web_ok and native_ok))
    )
    return {
        "verdict": "PASS" if contract_ok else "FAIL",
        "backend": "PUBLISH" if backend_should_publish else "WITHHOLD",
        "web": "RENDER" if web_ok else "WITHHOLD",
        "native": "RENDER" if native_ok else "WITHHOLD",
        "reason_codes": list(dict.fromkeys(reasons)),
    }
