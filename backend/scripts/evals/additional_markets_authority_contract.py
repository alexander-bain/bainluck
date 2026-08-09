"""Canonical render authority for the event page's Additional Markets section.

Extends the event-page membership/display domain with probability presence,
lifecycle, duplicate attribution, and two-sided-filter invariants.
"""

from __future__ import annotations

from typing import Any


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    rows = case.get("rows") or []

    for row in rows:
        probability = row.get("probability")
        if probability is None and row.get("rendered_probability") is not None:
            reasons.add("MISSING_PROBABILITY_FABRICATED")
        if isinstance(probability, (int, float)) and not 0 <= probability <= 1:
            reasons.add("PROBABILITY_OUT_OF_RANGE")

    status = case.get("event_status")
    if status in {"completed", "closed", "settled"}:
        for row in rows:
            if row.get("rendered_probability") is not None and not row.get("graded_result"):
                reasons.add("SETTLED_ROW_RENDERED_AS_LIVE_PRICE")

    for group in case.get("duplicate_groups") or []:
        distinct_sources = len(set(group.get("sources") or []))
        if group.get("badge_count", 1) != max(distinct_sources, 1):
            reasons.add("SOURCE_BADGE_COUNTS_ROWS_NOT_SOURCES")
        probs = [p for p in group.get("probabilities") or [] if p is not None]
        if len(probs) != len(group.get("probabilities") or []):
            if group.get("rendered_probability") is not None:
                reasons.add("PARTIAL_NULL_DUPLICATE_ADJUDICATED")
        elif probs and max(probs) - min(probs) > case.get("agreement_tolerance", 0.02):
            if group.get("rendered_probability") is not None:
                reasons.add("CONFLICTING_DUPLICATE_ADJUDICATED")

    for market in case.get("two_sided_candidates") or []:
        if market.get("filtered_as_hero") and not market.get("hero_identity_proven"):
            reasons.add("UNRELATED_TWO_ROW_MARKET_FILTERED")

    expected = case.get("expected_reachable_rows")
    if expected is not None and case.get("reachable_rows") != expected:
        reasons.add("ROW_RETENTION_MISMATCH")

    return {
        "verdict": "ALLOW" if not reasons else "REFUSE",
        "reasons": sorted(reasons),
    }
