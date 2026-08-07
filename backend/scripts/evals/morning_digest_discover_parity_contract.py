"""Oracle for Morning Digest versus Discover serving parity.

The contract is intentionally independent of application imports. A digest may
select a candidate only when the current Discover serving authority would emit
the same story. Suppression reasons remain typed so follow-up work can share one
eligibility result instead of recreating filters in the notification task.
"""

from __future__ import annotations


def evaluate(case: dict) -> dict:
    reasons: list[str] = []

    if case.get("partial_failure"):
        reasons.append("candidate_unverified")
    if case.get("status") != "open" or case.get("resolved"):
        reasons.append("not_open")
    if case.get("resolution_past") or case.get("title_implied_stale"):
        reasons.append("stale")
    if case.get("completed_event"):
        reasons.append("completed_event")
    if case.get("quality") == "suppress":
        reasons.append("quality_suppressed")

    probabilities = [p for p in case.get("probabilities", []) if p is not None]
    if not probabilities or max(probabilities, default=0) < 0.005:
        reasons.append("no_real_price")

    leader = max(probabilities, default=0)
    movement = abs(float(case.get("max_abs_movement_24h") or 0))
    volume = float(case.get("volume_24h") or 0)
    locked = leader >= 0.99 or leader <= 0.01
    if locked and movement < 0.10 and volume < 25000:
        reasons.append("locked_near_certain")

    if case.get("duplicate_story") or case.get("duplicate_event_family"):
        reasons.append("duplicate_family")
    if case.get("malformed_label"):
        reasons.append("malformed_label")
    if case.get("digest_score_fresh") is False:
        reasons.append("stale_digest_score")
    if case.get("survived_current_discover") is False:
        reasons.append("not_in_current_discover")

    reasons = list(dict.fromkeys(reasons))
    return {
        "verdict": "REFUSE" if reasons else "ALLOW",
        "reason_codes": reasons,
    }


def evaluate_corpus(cases: list[dict]) -> list[dict]:
    return [{"id": case["id"], **evaluate(case)} for case in cases]

