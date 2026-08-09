"""Desired event-concept terminal contract for UX-P031 review.

Dependency-free oracle. The serving UI needs four semantic states: data, loading,
definitively absent, and temporarily unavailable. Collapsing the last two makes a
backend outage look like a dead event link.
"""

from __future__ import annotations

from typing import Any


def verdict(case: dict[str, Any]) -> dict[str, str]:
    if case.get("has_data"):
        return {"state": "ready", "reason": "data_wins"}

    status = case.get("error_status")
    has_error = bool(case.get("has_error"))
    if status == 404:
        return {"state": "not_found", "reason": "definitive_404"}

    if has_error:
        if case.get("retries_exhausted") or case.get("ceiling_reached"):
            return {"state": "unavailable", "reason": "temporary_failure_exhausted"}
        return {"state": "loading", "reason": "temporary_failure_retrying"}

    if case.get("is_loading") or case.get("is_validating"):
        return {"state": "loading", "reason": "request_in_flight"}

    return {"state": "not_found", "reason": "empty_settled"}
