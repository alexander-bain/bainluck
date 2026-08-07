"""Dependency-free oracle for ESPN live-capture continuity and alert truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURES = Path(__file__).resolve().parents[2] / "tests/evals/fixtures/espn_live_capture_continuity_contract.json"


def decide(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("identity_valid") is False:
        return {"verdict": "refuse", "reason": "identity_or_orientation_invalid"}
    if case.get("supported_sport") is False:
        return {"verdict": "refuse", "reason": "unsupported_sport"}
    if case.get("clock_valid") is False:
        return {"verdict": "refuse", "reason": "invalid_time_boundary"}

    live = int(case.get("eligible_live_games", 0))
    attempted = int(case.get("attempted_games", 0))
    committed = int(case.get("committed_games", 0))
    fresh = int(case.get("fresh_games", committed))
    errors = int(case.get("errors", 0))

    if case.get("worker_alive") is False or case.get("beat_alive") is False:
        return {"verdict": "red", "reason": "dispatch_or_worker_dead"}
    if case.get("overlap") or case.get("timeout") or case.get("commit_failed"):
        return {"verdict": "red", "reason": "run_not_durably_complete"}
    if case.get("upstream_state") in {"error", "malformed", "stale", "unknown"}:
        return {"verdict": "unknown", "reason": "upstream_not_authoritative"}
    if live == 0:
        return {"verdict": "unknown", "reason": "empty_slate"}
    if attempted < live:
        return {"verdict": "red", "reason": "eligible_games_unattempted"}
    if errors or committed < live or fresh < live:
        return {"verdict": "red", "reason": "capture_incomplete"}
    if case.get("metrics_recorded_before_commit"):
        return {"verdict": "red", "reason": "success_not_commit_bound"}
    if case.get("duplicate_points"):
        return {"verdict": "red", "reason": "non_idempotent_retry"}
    return {"verdict": "green", "reason": "all_eligible_games_committed_fresh"}


def recovery(case: dict[str, Any]) -> dict[str, str]:
    if case.get("authoritative_history") is True and case.get("identity_valid") is True:
        return {"verdict": "recoverable", "reason": "authoritative_history_and_identity"}
    if case.get("authoritative_history") is False:
        return {"verdict": "lost", "reason": "upstream_history_absent"}
    return {"verdict": "refuse", "reason": "recovery_authority_unproven"}


def evaluate(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in pack["cases"]:
        actual = recovery(case) if case["kind"] == "recovery" else decide(case)
        rows.append({"id": case["id"], "passed": actual == case["expected"], "actual": actual})
    return {"total": len(rows), "passed": sum(r["passed"] for r in rows), "cases": rows}


def load() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


if __name__ == "__main__":
    print(json.dumps(evaluate(load()), indent=2, sort_keys=True))
