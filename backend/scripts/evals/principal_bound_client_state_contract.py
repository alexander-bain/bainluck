"""Pure oracle for client state publication and mutation across principals."""

from __future__ import annotations


def evaluate(case: dict) -> dict:
    current = case.get("current_principal")
    owner = case.get("state_owner")
    dispatch = case.get("dispatch_principal")
    completion = case.get("completion_principal")
    reasons: list[str] = []

    if owner not in {None, "anonymous", current}:
        reasons.append("foreign_state_visible")
    if case.get("cache_key_principal") not in {None, "anonymous", current}:
        reasons.append("foreign_cache_key")
    if case.get("published") and dispatch != current:
        reasons.append("stale_response_published")
    if case.get("mutation_sent") and dispatch != current:
        reasons.append("mutation_subject_changed")
    if case.get("timer_pending") and completion != dispatch:
        reasons.append("delayed_write_crossed_principal")
    if case.get("migration_consumed_by") not in {None, current}:
        reasons.append("foreign_migration_marker")
    if case.get("ownership_unknown") and (case.get("published") or case.get("mutation_sent")):
        reasons.append("unknown_owner_not_withheld")

    return {"verdict": "REFUSE" if reasons else "ALLOW", "reason_codes": reasons}

