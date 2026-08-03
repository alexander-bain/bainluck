"""Dependency-free C140 oracle for tournament browser evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "tournament-browser-evidence-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "tournament_browser_evidence_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)):
        raise ValueError("CASE_IDS_INVALID")
    defaults = payload.get("defaults") or {}
    payload["cases"] = [{**defaults, **row} for row in cases]
    return payload


def refusal_codes(row: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    if row.get("route_authority") not in {"committed", "observed"}:
        codes.append("ROUTE_NOT_OBSERVABLE")
    if not row.get("domain_matches", True):
        codes.append("WRONG_DOMAIN")
    if row.get("requested_sha") != row.get("observed_sha"):
        codes.append("SHA_MISMATCH")
    if row.get("selected_journeys", 0) < 1:
        codes.append("ZERO_JOURNEYS")
    if row.get("run_state") in {"cancelled", "superseded"}:
        codes.append("RUN_NOT_COMPLETE")
    if row.get("owner_count") != 1:
        codes.append("EVIDENCE_OWNER_INVALID")
    if row.get("terminal") != "real_content":
        codes.append("TERMINAL_NOT_REAL_CONTENT")
    if set(row.get("viewports") or []) != {"desktop", "mobile"}:
        codes.append("VIEWPORT_COVERAGE_INCOMPLETE")
    artifacts = set(row.get("artifacts") or [])
    if "screenshot" not in artifacts or not row.get("screenshot_hash"):
        codes.append("SCREENSHOT_EVIDENCE_MISSING")
    if "trace" in artifacts:
        codes.append("UNCONTAINED_TRACE_ARTIFACT")
    if not row.get("console_network_checked"):
        codes.append("CONSOLE_NETWORK_UNCHECKED")
    if row.get("console_errors"):
        codes.append("CONSOLE_FAILURE")
    if row.get("network_errors"):
        codes.append("NETWORK_FAILURE")
    if row.get("mobile_overflow"):
        codes.append("MOBILE_OVERFLOW")
    if not row.get("adjacent_regression"):
        codes.append("ADJACENT_REGRESSION_MISSING")
    if not row.get("artifact_upload_complete"):
        codes.append("ARTIFACT_UPLOAD_INCOMPLETE")
    return sorted(set(codes))


def classify(row: dict[str, Any]) -> str:
    return "SHIPPED_GOOD" if not refusal_codes(row) else "NOT_OBSERVABLE"


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    results = []
    for row in corpus["cases"]:
        actual = refusal_codes(row)
        expected = sorted(row.get("expected_refusals") or [])
        status = classify(row)
        ok = actual == expected and status == row.get("expected_status")
        results.append({"id": row["id"], "ok": ok, "actual": actual, "status": status})
    return {"total": len(results), "passed": sum(x["ok"] for x in results), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
