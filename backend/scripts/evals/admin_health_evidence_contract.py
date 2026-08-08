"""Dependency-free oracle for evidence-backed admin health headlines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/admin_health_evidence_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "admin-health-evidence/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(v, str) or not v for v in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    e = row["evidence"]
    required = e.get("required", [])
    optional = e.get("optional", [])
    reasons: list[str] = []

    if e.get("worker_heartbeat") in {"missing", "stale", "error"}:
        reasons.append("WORKER_HEARTBEAT_UNAVAILABLE")
    if e.get("cache_read") == "error":
        reasons.append("CACHE_READ_FAILED")
    if e.get("db_read") == "error":
        reasons.append("DB_READ_FAILED")
    if e.get("registry_complete") is False:
        reasons.append("REQUIRED_CAPABILITY_UNREGISTERED")
    if e.get("latest_verdict") in {"failed", "partial", "unknown"}:
        reasons.append("LATEST_RUN_NOT_COMPLETE")

    stale = [s for s in required if s.get("state") == "stale"]
    unknown = [s for s in required if s.get("state") in {"unknown", "no_data", "error"}]
    red = [s for s in required if s.get("state") in {"red", "critical", "failed"}]
    degraded = [s for s in required if s.get("state") in {"amber", "degraded", "partial"}]
    green = [s for s in required if s.get("state") in {"green", "healthy", "complete"}]
    if stale:
        reasons.append("STALE_REQUIRED_EVIDENCE")
    if unknown:
        reasons.append("REQUIRED_EVIDENCE_UNKNOWN")
    if not required and optional:
        reasons.append("OPTIONAL_ONLY_EVIDENCE")

    if red or e.get("worker_heartbeat") == "stale":
        headline, alert = "red", "critical"
    elif degraded or e.get("latest_verdict") in {"failed", "partial"}:
        headline, alert = "amber", "degraded"
    elif reasons or len(green) != len(required) or not required:
        headline, alert = "unknown", "unknown"
    else:
        headline, alert = "green", "none"

    complete = headline in {"green", "red", "amber"} and not any(
        code in reasons for code in {
            "CACHE_READ_FAILED", "DB_READ_FAILED", "REQUIRED_CAPABILITY_UNREGISTERED",
            "REQUIRED_EVIDENCE_UNKNOWN", "OPTIONAL_ONLY_EVIDENCE", "STALE_REQUIRED_EVIDENCE",
            "WORKER_HEARTBEAT_UNAVAILABLE",
        }
    )
    classification = (
        "EVIDENCE_BACKED" if complete else
        "STALE_AUTHORITY" if "STALE_REQUIRED_EVIDENCE" in reasons else
        "UNKNOWN_HONEST"
    )
    return {
        "classification": classification,
        "headline": headline,
        "evidence_complete": complete,
        "alert_state": alert,
        "reason_codes": sorted(set(reasons)),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda item: item["id"]):
        actual = evaluate_case(row)
        details.append({"id": row["id"], "actual": actual, "expected": row["expected"], "passed": actual == row["expected"]})
    return {"schema_version": payload["schema_version"], "total": len(details), "passed": sum(x["passed"] for x in details), "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
