"""Dependency-free oracle for empty, partial, stale, and unavailable surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/absence_semantics_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "absence-semantics-contract/v1":
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


def decide(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row["evidence"]
    result = row["result"]
    reasons: list[str] = []
    items = int(evidence.get("items", 0))
    complete = evidence.get("complete") is True
    degraded = evidence.get("degraded") is True
    authority = evidence.get("authority") is True
    stale = evidence.get("last_good") is True
    errored = evidence.get("error") is True

    if stale and items:
        state, retryable, cacheable, severity = "STALE_RESULTS", True, True, "warning"
    elif errored or (not authority and not complete):
        state, retryable, cacheable, severity = "UNAVAILABLE", True, False, "error"
    elif degraded or evidence.get("primary_missing"):
        state = "PARTIAL" if items else "UNAVAILABLE"
        retryable, cacheable = True, False
        severity = "warning" if items else "error"
    elif complete and items:
        state, retryable, cacheable, severity = "RESULTS", False, True, "none"
    elif complete:
        state, retryable, cacheable, severity = "EMPTY", False, True, "none"
    else:
        state, retryable, cacheable, severity = "UNKNOWN", True, False, "warning"

    if result.get("display_state") != state:
        reasons.append("DISPLAY_STATE_DISHONEST")
    if result.get("retryable") is not retryable:
        reasons.append("RETRYABILITY_DISHONEST")
    if result.get("cacheable") is not cacheable:
        reasons.append("CACHEABILITY_DISHONEST")
    if result.get("severity") != severity:
        reasons.append("SEVERITY_DISHONEST")
    if state in {"PARTIAL", "STALE_RESULTS", "UNAVAILABLE"} and not result.get("metadata_consumed"):
        reasons.append("DEGRADATION_METADATA_IGNORED")
    if evidence.get("debug_only") and result.get("metadata_consumed"):
        reasons.append("DEBUG_METADATA_CLAIMED_AS_SERVING")
    if evidence.get("native_expected") is not None and result.get("native_state") != evidence["native_expected"]:
        reasons.append("NATIVE_PARITY_DRIFT")

    return {
        "display_state": state,
        "retryable": retryable,
        "cacheable": cacheable,
        "severity": severity,
        "reason_codes": sorted(set(reasons)),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda item: item["id"]):
        actual = decide(row)
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
