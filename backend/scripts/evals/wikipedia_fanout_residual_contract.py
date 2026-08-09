"""Admission oracle for bounded third-party enrichment bursts."""

from __future__ import annotations

from typing import Iterable


def admitted_requests(outcomes: Iterable[str], threshold: int = 5) -> int:
    """Count requests when circuit state is rechecked at slot acquisition.

    Each outcome is ``success``, ``not_found``, or ``throw``. All calls may have
    been queued while closed; only calls admitted before the threshold execute.
    """
    failures = 0
    admitted = 0
    circuit_open = False
    for outcome in outcomes:
        if circuit_open:
            continue
        admitted += 1
        if outcome == "throw":
            failures += 1
            if failures >= threshold:
                circuit_open = True
        else:
            failures = 0
    return admitted
