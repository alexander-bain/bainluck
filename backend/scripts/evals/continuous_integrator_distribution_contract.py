"""Distribution/enforcement contract for standing executable process rulings."""

from __future__ import annotations


def verdict(*, ruling_tracked: bool, command_tracked: bool, ci_marker: bool, local_command_matches: bool) -> dict[str, str]:
    if not ruling_tracked:
        return {"verdict": "REFUSE", "reason": "ruling_not_distributed"}
    if not command_tracked:
        return {"verdict": "REFUSE", "reason": "implementation_not_distributed"}
    if not ci_marker:
        return {"verdict": "REFUSE", "reason": "claimed_guard_absent"}
    if not local_command_matches:
        return {"verdict": "REFUSE", "reason": "installed_command_drift"}
    return {"verdict": "ACCEPT", "reason": "distributed_and_guarded"}
