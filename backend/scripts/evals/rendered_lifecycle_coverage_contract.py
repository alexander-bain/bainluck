"""Authority for joining rendered cards to same-generation lifecycle evidence."""

from __future__ import annotations

from typing import Any


CARD_TYPES = {"event", "futures", "concept", "tournament", "grid", "comparison", "bundle"}
TERMINAL = {"completed", "closed", "resolved", "settled", "cancelled", "canceled"}


def evaluate(row: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    rendered_type = row.get("rendered_type")
    if rendered_type not in CARD_TYPES:
        reasons.add("CARD_TYPE_UNKNOWN")
    if row.get("recorded_type") != rendered_type:
        reasons.add("IMPRESSION_TYPE_DRIFT")
    if not row.get("stable_id") or row.get("recorded_id") != row.get("stable_id"):
        reasons.add("IMPRESSION_ID_DRIFT")

    authority = row.get("authority")
    state = "unknown"
    if not isinstance(authority, dict):
        reasons.add("LIFECYCLE_AUTHORITY_MISSING")
    else:
        if authority.get("generation") != row.get("render_generation"):
            reasons.add("LIFECYCLE_GENERATION_MISMATCH")
        status = str(authority.get("status") or "").lower()
        if not status:
            reasons.add("LIFECYCLE_STATUS_UNKNOWN")
        elif status in TERMINAL:
            state = "stale"
        else:
            state = "fresh"
        if authority.get("deadline_relation") == "past":
            state = "stale"

    cache = row.get("cache") or {}
    if cache.get("status") in {"hit", "stale_hit", "last_good"}:
        if not cache.get("lifecycle_revalidated"):
            reasons.add("CACHED_CARD_NOT_REVALIDATED")
        if cache.get("generated_at") is None:
            reasons.add("CACHE_GENERATION_TIME_MISSING")

    probability = row.get("probability")
    if probability is not None:
        if probability.get("value") is not None and probability.get("observed_at") is None:
            reasons.add("PROBABILITY_OBSERVATION_TIME_MISSING")
        if probability.get("age_seconds") is not None and probability.get("max_age_seconds") is not None and probability["age_seconds"] > probability["max_age_seconds"]:
            reasons.add("STALE_PROBABILITY_PRESENTED")

    if reasons & {"LIFECYCLE_AUTHORITY_MISSING", "LIFECYCLE_GENERATION_MISMATCH", "LIFECYCLE_STATUS_UNKNOWN", "CARD_TYPE_UNKNOWN", "IMPRESSION_TYPE_DRIFT", "IMPRESSION_ID_DRIFT"}:
        state = "unknown"
    verdict = "COUNT_FRESH" if not reasons and state == "fresh" else "COUNT_STALE" if not reasons and state == "stale" else "COUNT_UNKNOWN"
    return {"verdict": verdict, "reasons": sorted(reasons), "lifecycle_state": state}
