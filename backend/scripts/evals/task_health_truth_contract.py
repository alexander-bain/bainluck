"""Dependency-free evaluator for scheduled-task health history."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/task_health_truth_contract.json"
FAILURE_STATES = {"complete_failure", "cancelled", "soft_limit", "hard_kill"}
VALID_STATES = FAILURE_STATES | {"complete_success", "partial"}


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _finite_nonnegative(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and value >= 0
    )


def _validate_event(event: Any, schema: str) -> list[str]:
    if not isinstance(event, dict):
        return ["POISON_EVENT"]
    required = {"event_id", "schema_version", "at", "state", "duration_ms"}
    if required - event.keys():
        return ["EVENT_MISSING_FIELDS"]
    findings: list[str] = []
    if event["schema_version"] != schema:
        findings.append("EVENT_SCHEMA_MISMATCH")
    if not isinstance(event["event_id"], str) or not event["event_id"]:
        findings.append("INVALID_EVENT_ID")
    if _timestamp(event["at"]) is None:
        findings.append("INVALID_EVENT_TIMESTAMP")
    if event["state"] not in VALID_STATES:
        findings.append("INVALID_EVENT_STATE")
    if not _finite_nonnegative(event["duration_ms"]):
        findings.append("INVALID_EVENT_DURATION")
    return findings


def evaluate(case: dict[str, Any], pack_policy: dict[str, Any]) -> dict[str, Any]:
    policy = {**pack_policy, **case.get("policy", {})}
    findings: list[str] = []
    evaluation_at = _timestamp(case.get("evaluation_at"))
    if evaluation_at is None:
        findings.append("INVALID_EVALUATION_TIMESTAMP")
        evaluation_at = datetime.min.replace(tzinfo=timezone.utc)
    if case.get("schema_version") != policy["case_schema_version"]:
        findings.append("CASE_SCHEMA_MISMATCH")

    history_complete = case.get("history_complete")
    if not isinstance(history_complete, bool):
        findings.append("INVALID_HISTORY_COMPLETENESS")
    schedule = case.get("schedule")
    if not isinstance(schedule, dict) or not _finite_nonnegative(schedule.get("interval_hours")) or schedule.get("interval_hours") == 0:
        findings.append("INVALID_SCHEDULE")
        schedule = {"interval_hours": 1, "freshness_hours": 1}
    elif not _finite_nonnegative(schedule.get("freshness_hours")):
        findings.append("INVALID_FRESHNESS_POLICY")

    events = case.get("events")
    if not isinstance(events, list):
        findings.append("EVENTS_WRONG_SHAPE")
        events = []
    valid: list[tuple[datetime, dict[str, Any]]] = []
    ids: set[str] = set()
    for event in events:
        event_findings = _validate_event(event, policy["event_schema_version"])
        findings.extend(event_findings)
        if event_findings:
            continue
        if event["event_id"] in ids:
            findings.append("DUPLICATE_EVENT_ID")
            continue
        ids.add(event["event_id"])
        at = _timestamp(event["at"])
        if at > evaluation_at + timedelta(seconds=policy["future_tolerance_seconds"]):
            findings.append("FUTURE_EVENT")
        valid.append((at, event))
    valid.sort(key=lambda row: (row[0], row[1]["event_id"]))
    for index in range(1, len(valid)):
        previous_at, previous = valid[index - 1]
        current_at, _ = valid[index]
        previous_start = previous_at - timedelta(milliseconds=previous["duration_ms"])
        current_start = current_at - timedelta(milliseconds=valid[index][1]["duration_ms"])
        if current_start < previous_at and previous_start < current_at:
            findings.append("OVERLAPPING_RUNS")

    lower = evaluation_at - timedelta(hours=policy["window_hours"])
    window = [event for at, event in valid if lower < at <= evaluation_at]
    successes = sum(event["state"] == "complete_success" for event in window)
    failures = sum(event["state"] in FAILURE_STATES for event in window)
    partials = sum(event["state"] == "partial" for event in window)
    terminal = successes + failures
    failure_ratio = round(failures / terminal, 6) if terminal else None

    last_event = valid[-1][1] if valid else None
    consecutive_failures = 0
    for _, event in reversed(valid):
        if event["state"] == "complete_success":
            break
        if event["state"] in FAILURE_STATES:
            consecutive_failures += 1

    reasons: list[str] = []
    health = "healthy"
    if findings:
        health, reasons = "unknown", sorted(set(findings))
    elif not history_complete:
        health, reasons = "unknown", ["HISTORY_INCOMPLETE"]
    elif last_event is None:
        health, reasons = "unknown", ["NEVER_RUN"]
    else:
        last_at = _timestamp(last_event["at"])
        age_hours = (evaluation_at - last_at).total_seconds() / 3600
        if age_hours > schedule["freshness_hours"]:
            health, reasons = "critical", ["STALE_LAST_TERMINAL"]
        elif consecutive_failures >= policy["critical_consecutive_failures"]:
            health, reasons = "critical", ["CONSECUTIVE_FAILURES_CRITICAL"]
        elif failure_ratio is not None and failure_ratio >= policy["critical_failure_ratio"]:
            health, reasons = "critical", ["ROLLING_FAILURE_RATIO_CRITICAL"]
        elif consecutive_failures >= policy["degraded_consecutive_failures"]:
            health, reasons = "degraded", ["CONSECUTIVE_FAILURES_DEGRADED"]
        elif failure_ratio is not None and failure_ratio >= policy["degraded_failure_ratio"]:
            health, reasons = "degraded", ["ROLLING_FAILURE_RATIO_DEGRADED"]
        elif partials:
            health, reasons = "degraded", ["INCOMPLETE_RUNS"]

    return {
        "rolling": {
            "successes": successes,
            "failures": failures,
            "partials": partials,
            "terminal": terminal,
            "failure_ratio": failure_ratio,
            "boundary": "(evaluation_at-window, evaluation_at]",
        },
        "last_terminal_state": last_event["state"] if last_event else None,
        "consecutive_failures": consecutive_failures,
        "freshness": (
            "unknown" if last_event is None
            else "fresh" if (evaluation_at - _timestamp(last_event["at"])).total_seconds() / 3600 <= schedule["freshness_hours"]
            else "stale"
        ),
        "completeness": "complete" if history_complete else "unknown",
        "health": health,
        "reasons": reasons,
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    results = []
    for case in pack.get("cases", []):
        result = evaluate(case, pack["policy"])
        mismatches = [key for key, value in case.get("expected", {}).items() if result.get(key) != value]
        results.append({"id": case.get("id"), **result, "expected_mismatches": mismatches})
    return {
        "contract_version": pack["policy"]["contract_version"],
        "cases": len(results),
        "passed": sum(not row["expected_mismatches"] for row in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['passed']}/{result['cases']} task-health contract cases passed")
        for row in result["results"]:
            if row["expected_mismatches"]:
                print(f"FAIL {row['id']}: {row['expected_mismatches']}")
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
