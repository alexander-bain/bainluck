"""Failure-semantics oracle for search enrichment stages.

Search's optional odds/GEI/team enrichment must not make an otherwise valid
entity result unavailable. Query timeouts degrade the named stage; programming
or integrity errors still surface.
"""

from __future__ import annotations


OPTIONAL_STAGES = {"event_odds", "event_gei", "event_teams", "futures", "teams"}


def outcome(*, stage: str, failure: str | None, has_base_results: bool = True) -> dict:
    if failure is None:
        return {"http": 200, "base_results": has_base_results, "degraded": []}
    if failure != "query_timeout":
        return {"http": 500, "base_results": False, "degraded": []}
    if stage not in OPTIONAL_STAGES:
        return {"http": 500, "base_results": False, "degraded": []}
    return {"http": 200, "base_results": has_base_results, "degraded": [stage]}
