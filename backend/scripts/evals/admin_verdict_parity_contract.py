"""Dependency-free oracle for verdict parity across admin health surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/admin_verdict_parity_contract.json"
SURFACES = ("api", "cockpit", "dedicated", "ops_snapshot")


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "admin-verdict-parity/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [r.get("id") for r in cases if isinstance(r, dict)]
    if len(ids) != len(cases) or any(not isinstance(v, str) or not v for v in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    e = row["evidence"]
    reasons: list[str] = []
    if e.get("dependency") == "unreadable":
        canonical = "unknown"
        reasons.append("DEPENDENCY_UNREADABLE")
    elif e.get("worker") == "down":
        canonical = "red"
        reasons.append("WORKER_DOWN")
    elif e.get("timestamp") in {"missing", "invalid"}:
        canonical = "unknown"
        reasons.append("FRESHNESS_UNKNOWN")
    elif e.get("stale"):
        canonical = "red"
        reasons.append("EVIDENCE_SILENT")
    elif e.get("verdict") in {"red", "failed", "critical"}:
        canonical = "red"
    elif e.get("verdict") in {"amber", "yellow", "partial", "degraded", "unknown"}:
        canonical = "amber" if e.get("verdict") != "unknown" else "unknown"
    elif e.get("skipped") or e.get("explained_artifact"):
        canonical = "amber"
        reasons.append("NON_CLEAN_EVIDENCE")
    elif e.get("verdict") in {"green", "healthy", "complete"}:
        canonical = "green"
    else:
        canonical = "unknown"
        reasons.append("VERDICT_MISSING")

    intentional = e.get("intentional_scope")
    states = {surface: canonical for surface in SURFACES}
    if intentional:
        surface = intentional["surface"]
        states[surface] = intentional["state"]
        reasons.append("INTENTIONAL_SCOPE")
    return {
        "canonical_verdict": canonical,
        "surface_states": states,
        "parity": "INTENTIONAL_SCOPE" if intentional else "SHARED_CONTRACT",
        "reason_codes": sorted(reasons),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda x: x["id"]):
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
