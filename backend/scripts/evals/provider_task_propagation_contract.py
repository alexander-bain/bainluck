"""Dependency-free oracle for provider outcomes propagated through task health."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/provider_task_propagation_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "provider-task-propagation/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    run = row["run"]
    outcome = run["provider_outcome"]
    optional = run.get("provider_role") == "optional"
    mixed = run.get("successful_siblings", 0) > 0
    last_good = run.get("last_good", False)
    eligible = run.get("eligible", True)
    repeated = run.get("repeated_degraded", False)

    reasons: list[str] = []
    if not eligible:
        classification, verdict = "TRUE_EMPTY", "complete"
        cursor, metrics, alert, cache, display = "hold", "success", "none", "preserve", "empty"
        reasons.append("NOTHING_ELIGIBLE")
    elif outcome in {"empty", "absent"}:
        classification, verdict = "TRUE_EMPTY", "complete"
        cursor, metrics, alert, cache, display = "advance", "success", "none", "replace", "empty"
        reasons.append("AUTHORITATIVE_EMPTY")
    elif outcome == "success":
        classification, verdict = "TRUE_EMPTY", "complete"
        cursor, metrics, alert, cache, display = "advance", "success", "none", "replace", "fresh"
    elif outcome in {"error", "invalid", "cache_miss"}:
        classification = "DEGRADED_VISIBLE" if optional else "AUTHORITY_LOSS"
        verdict = "partial" if optional or mixed else "failed"
        cursor, metrics = "hold", "incomplete" if verdict == "partial" else "failure"
        alert = "degraded" if optional or mixed else "critical"
        cache = "serve_stale" if last_good else "preserve"
        display = "stale" if last_good else ("partial" if optional or mixed else "unavailable")
        reasons.append("PROVIDER_UNAVAILABLE")
    elif outcome in {"partial", "poison_row"}:
        classification, verdict = "DEGRADED_VISIBLE", "partial"
        cursor, metrics, alert, cache, display = "hold", "incomplete", "degraded", "preserve", "partial"
        reasons.append("PROVIDER_PARTIAL")
    else:
        raise ValueError(f"PROVIDER_OUTCOME_INVALID:{outcome}")

    if repeated and alert != "none":
        alert = "critical"
        reasons.append("REPEATED_DEGRADATION")

    return {
        "classification": classification,
        "task_verdict": verdict,
        "cursor_action": cursor,
        "metrics_action": metrics,
        "alert_state": alert,
        "cache_action": cache,
        "display_state": display,
        "reason_codes": sorted(reasons),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda item: item["id"]):
        actual = evaluate_case(row)
        details.append({"id": row["id"], "actual": actual, "expected": row["expected"], "passed": actual == row["expected"]})
    return {"schema_version": payload["schema_version"], "total": len(details), "passed": sum(item["passed"] for item in details), "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
