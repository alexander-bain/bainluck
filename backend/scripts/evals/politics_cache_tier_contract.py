"""Authority for politics primary/stale/live cache-tier behavior."""

from __future__ import annotations

from typing import Any


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    primary = case.get("primary") or {}
    stale = case.get("stale") or {}
    selected = "live"

    if primary.get("read") == "value" and primary.get("valid"):
        selected = "primary"
    elif stale.get("read") == "value" and stale.get("valid"):
        selected = "stale"

    if primary.get("read") == "value" and not primary.get("valid") and not case.get("continued_to_stale"):
        reasons.add("MALFORMED_PRIMARY_BLOCKS_FALLBACK")
    if selected == "stale":
        if not case.get("cache_status_exposed"):
            reasons.add("STALE_STATUS_HIDDEN")
        if not case.get("generated_at_exposed"):
            reasons.add("STALE_AGE_HIDDEN")
        age = stale.get("age_seconds")
        if not isinstance(age, (int, float)):
            reasons.add("STALE_AGE_UNKNOWN")
        elif age > case.get("max_stale_age_seconds", 86400):
            reasons.add("STALE_TOO_OLD")
    if selected == "live":
        if case.get("concurrent_builders", 1) > 1 and not case.get("singleflight"):
            reasons.add("COLD_REBUILD_STAMPEDE")
        writes = set(case.get("writes") or [])
        if case.get("live_build_complete") and writes != {"primary", "stale"}:
            reasons.add("LIVE_PUBLICATION_ASYMMETRIC")
        if not case.get("live_build_complete") and writes:
            reasons.add("INCOMPLETE_BUILD_PUBLISHED")
    if case.get("redis_read") == "unavailable" and case.get("classified_as") == "miss":
        reasons.add("REDIS_OUTAGE_COLLAPSED_TO_MISS")
    if case.get("write_failed") and not case.get("response_preserved"):
        reasons.add("CACHE_WRITE_FAILURE_BROKE_RESPONSE")
    if case.get("connection_opened") and not case.get("connection_closed"):
        reasons.add("CONNECTION_LEAK")
    return {"verdict": "ALLOW" if not reasons else "REFUSE", "reasons": sorted(reasons), "selected_tier": selected}
