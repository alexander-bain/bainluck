"""Pure contract for admin headline truth and navigation reachability."""

from __future__ import annotations


SEVERITY = {"unknown": 0, "good": 1, "warning": 2, "critical": 3}


def aggregate_headline(child_states: list[str]) -> str:
    """A parent may never be healthier than its worst product-relevant child."""
    if not child_states:
        return "unknown"
    return max(child_states, key=lambda state: SEVERITY[state])


def classification_tone(unclassified_rate: float) -> str:
    if unclassified_rate > 0.30:
        return "critical"
    if unclassified_rate > 0.15:
        return "warning"
    return "good"


def labeling_sufficiency(*, insufficient_strata: int, empty_queues: int, census_complete: bool) -> str:
    if not census_complete:
        return "unknown"
    if empty_queues > 0 or insufficient_strata > 0:
        return "warning"
    return "good"


def navigation_verdict(*, operational_pages: set[str], linked_pages: set[str]) -> dict:
    missing = sorted(operational_pages - linked_pages)
    return {"verdict": "REFUSE" if missing else "ACCEPT", "missing": missing}
