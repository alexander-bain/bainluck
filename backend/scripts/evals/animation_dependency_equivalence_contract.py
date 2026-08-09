"""Frontend-performance extension of canonical first_card_client_contract.

An optional animation split may reduce bytes, but it must not gate content,
change interaction semantics, or claim that statically imported code vanished.
"""

from __future__ import annotations

from typing import Any


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()

    if case.get("content_ready") and not case.get("content_visible"):
        if case.get("waiting_for_animation_chunk"):
            reasons.add("ANIMATION_CHUNK_GATES_CONTENT")
        else:
            reasons.add("CONTENT_VISIBILITY_REGRESSION")
    if case.get("animation_chunk_failed") and not case.get("content_visible"):
        reasons.add("OPTIONAL_CHUNK_FAILURE_HIDES_CONTENT")
    if case.get("initial_hidden") and not case.get("no_motion_fallback_visible"):
        reasons.add("INITIAL_STATE_HAS_NO_VISIBLE_FALLBACK")
    if case.get("claims_dependency_absent") and case.get("static_dependency_imports"):
        reasons.add("BUNDLE_CLAIM_EXCEEDS_IMPORT_GRAPH")
    if case.get("multiple_providers", 1) > 1 and not case.get("loader_dedup_proven"):
        reasons.add("FEATURE_LOADER_FANOUT_UNPROVEN")
    if case.get("dom_changed") or case.get("focus_order_changed") or case.get("controls_changed"):
        reasons.add("BEHAVIORAL_PARITY_BROKEN")
    if case.get("reduced_motion") and not case.get("content_visible"):
        reasons.add("REDUCED_MOTION_HIDES_CONTENT")
    if case.get("measured_before_kb") is not None and case.get("measured_after_kb") is not None:
        if case["measured_after_kb"] >= case["measured_before_kb"]:
            reasons.add("NO_MEASURED_BUNDLE_IMPROVEMENT")

    return {"verdict": "ALLOW" if not reasons else "REFUSE", "reasons": sorted(reasons)}
