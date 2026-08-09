"""Canonical contract for health surfaces that must distinguish clean from unreadable.

Extends the admin-health evidence domain with LAT-P017 transaction, completeness,
freshness-population, and coverage-union invariants.
"""

from __future__ import annotations

from typing import Any


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()

    panels = case.get("panels") or []
    poisoned = False
    for panel in panels:
        outcome = panel.get("outcome")
        if poisoned and outcome == "cascade_failure":
            reasons.add("PANEL_FAILURE_CASCADED")
        if outcome == "timeout":
            if not panel.get("error_exposed"):
                reasons.add("PANEL_FAILURE_PRESENTED_AS_EMPTY")
            if not panel.get("rolled_back"):
                reasons.add("PANEL_FAILURE_NOT_ISOLATED")
                poisoned = True
        if panel.get("timeout_local") and not panel.get("scope_closed"):
            reasons.add("PANEL_TIMEOUT_SCOPE_LEAKED")

    configured = set(case.get("configured_checks") or [])
    completed = set(case.get("completed_checks") or [])
    claimed = case.get("claimed_status")
    if configured - completed and claimed == "green":
        reasons.add("RUN_COMPLETENESS_HIDDEN")
    if case.get("check_skipped") and claimed == "green":
        reasons.add("SKIPPED_CHECK_CLAIMED_GREEN")
    if case.get("real_defects", 0) and claimed != "red":
        reasons.add("REAL_DEFECT_NOT_RED")
    if case.get("close_issue") and (claimed != "green" or configured - completed):
        reasons.add("UNVERIFIED_RUN_CLOSED_ISSUE")

    freshness_rows = case.get("freshness_rows") or []
    if freshness_rows:
        open_rows = [r for r in freshness_rows if r.get("status") == "open"]
        selected = max(
            (r.get("updated_at", -1) for r in freshness_rows), default=-1
        )
        open_selected = max(
            (r.get("updated_at", -1) for r in open_rows), default=-1
        )
        if selected != open_selected:
            reasons.add("CLOSED_MARKET_MASKED_OPEN_FRESHNESS")

    source_sets = case.get("source_sets") or []
    if source_sets:
        true_union = len(set().union(*(set(rows) for rows in source_sets)))
        reported = case.get("reported_coverage")
        if reported != true_union:
            reasons.add("COVERAGE_UNION_UNDERCOUNTED")

    return {
        "verdict": "ALLOW" if not reasons else "REFUSE",
        "reasons": sorted(reasons),
    }
