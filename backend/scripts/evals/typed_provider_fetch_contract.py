"""Dependency-free oracle for typed provider fetch and consumer semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/typed_provider_fetch_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "typed-provider-fetch-contract/v1":
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
    fetch = row["fetch"]
    status = fetch["status"]
    role = fetch.get("role", "primary")
    retries_exhausted = fetch.get("retries_exhausted", False)
    partial = fetch.get("partial", False)
    stale_available = fetch.get("stale_available", False)

    if status == "ok":
        outcome = "partial" if partial else ("empty" if fetch.get("empty") else "success")
        retryable = False
        reasons = ["PARTIAL_PAGE"] if partial else []
    elif status in {"404", "410"}:
        outcome, retryable, reasons = "absent", False, ["AUTHORITATIVE_ABSENCE"]
    elif status in {"429", "5xx", "timeout", "network"}:
        outcome, retryable, reasons = "error", True, ["UPSTREAM_RETRYABLE"]
        if retries_exhausted:
            reasons.append("RETRIES_EXHAUSTED")
    elif status in {"malformed", "schema"}:
        outcome, retryable, reasons = "error", False, ["UPSTREAM_INVALID"]
    elif status == "poison_row":
        outcome, retryable, reasons = "partial", False, ["POISON_ROW_ISOLATED"]
    elif status == "cache_miss":
        outcome, retryable, reasons = "cache_miss", True, ["CACHE_MISS"]
    else:
        raise ValueError(f"STATUS_INVALID:{status}")

    if outcome in {"error", "cache_miss"}:
        cursor_action = "hold"
        cache_action = "serve_stale" if stale_available else "preserve"
        display_state = "stale" if stale_available else ("degraded" if role == "optional" else "unavailable")
        task_verdict = "degraded" if role == "optional" else "failed"
    elif outcome == "partial":
        cursor_action, cache_action, display_state, task_verdict = "hold", "preserve", "partial", "degraded"
    elif outcome == "absent":
        cursor_action, cache_action, display_state, task_verdict = "advance", "invalidate", "absent", "complete"
    else:
        cursor_action, cache_action = "advance", "replace"
        display_state = "empty" if outcome == "empty" else "fresh"
        task_verdict = "complete"

    return {
        "typed_outcome": outcome,
        "retryable": retryable,
        "cursor_action": cursor_action,
        "cache_action": cache_action,
        "display_state": display_state,
        "task_verdict": task_verdict,
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
