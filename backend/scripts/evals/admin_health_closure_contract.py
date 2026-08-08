"""End-to-end closure oracle for provider-to-admin health truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/admin_health_closure_contract.json"
LOWER_FIXTURES = Path(__file__).parents[2] / "tests/evals/fixtures"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "admin-health-closure/v1":
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


def lower_fixture_index() -> dict[str, set[str]]:
    files = {
        "fetch": "typed_provider_fetch_contract.json",
        "task": "provider_task_propagation_contract.json",
        "health": "admin_health_evidence_contract.json",
        "age": "evidence_age_contract.json",
        "parity": "admin_verdict_parity_contract.json",
    }
    return {
        name: {r["id"] for r in json.loads((LOWER_FIXTURES / filename).read_text(encoding="utf-8"))["cases"]}
        for name, filename in files.items()
    }


def evaluate_case(row: dict[str, Any], index: dict[str, set[str]] | None = None) -> dict[str, Any]:
    refs = row.get("composes", {})
    index = index or lower_fixture_index()
    missing = sorted(f"{layer}:{case_id}" for layer, case_id in refs.items() if case_id not in index.get(layer, set()))
    if missing:
        return {"verdict": "REFUSE", "missing_refs": missing, "reason_codes": ["LOWER_FIXTURE_MISSING"]}

    s = row["scenario"]
    provider = s["provider"]
    optional = s.get("optional", False)
    stale = s.get("stale", False)
    timestamp_valid = s.get("timestamp_valid", True)
    dependency_readable = s.get("dependency_readable", True)
    skipped = s.get("skipped", False)
    artifact = s.get("explained_artifact", False)
    last_good = s.get("last_good", False)

    if provider in {"empty", "absent", "success"}:
        helper = provider
        task = "complete"
        cursor = "advance"
        cache = "replace"
        canonical = "green"
        display = "empty" if provider != "success" else "fresh"
    elif optional:
        helper, task, cursor, cache, canonical, display = "error", "partial", "hold", "preserve", "amber", "partial"
    else:
        helper, task, cursor, cache, canonical, display = "error", "failed", "hold", "preserve", "red", "unavailable"

    reasons: list[str] = []
    if provider in {"timeout", "429", "5xx", "invalid", "cache_miss"}:
        helper = "error"
        reasons.append("PROVIDER_FAILURE_TYPED")
    if last_good and helper == "error":
        cache, display = "serve_stale", "stale"
    if skipped or artifact:
        canonical = "amber"
        reasons.append("NON_CLEAN_EVIDENCE")
    if not dependency_readable or not timestamp_valid:
        canonical = "unknown"
        reasons.append("EVIDENCE_UNVERIFIABLE")
    elif stale:
        canonical = "red"
        display = "stale"
        reasons.append("EVIDENCE_SILENT")

    return {
        "verdict": "PASS",
        "missing_refs": [],
        "helper_outcome": helper,
        "task_terminal": task,
        "cursor_action": cursor,
        "cache_action": cache,
        "canonical_health": canonical,
        "surface_states": {surface: canonical for surface in ("api", "cockpit", "dedicated", "ops_snapshot")},
        "display_state": display,
        "reason_codes": sorted(reasons),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    index = lower_fixture_index()
    details = []
    for row in sorted(payload["cases"], key=lambda x: x["id"]):
        actual = evaluate_case(row, index)
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
