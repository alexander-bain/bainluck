"""Dependency-free C138 contract for bounded curated-pick auto-application."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "curated-pick-auto-apply-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "curated_pick_auto_apply_contract.json"
BOOST = 8
CAP = 20
TTL_DAYS = 14
MATCH_THRESHOLD = 0.90


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
    return payload


def decide(row: dict[str, Any]) -> dict[str, Any]:
    mode = row.get("mode", "dry_run")
    if mode == "disabled":
        return _result("drop", "kill_switch_disabled", 0, 0)
    if row.get("storage_ok") is False:
        return _result("drop", "storage_unavailable", 0, 0)
    if row.get("batch_cancelled"):
        return _result("drop", "batch_cancelled", 0, 0)
    if row.get("malformed"):
        return _result("drop", "malformed_pick", 0, 0)

    lifecycle = row.get("lifecycle") or {}
    if lifecycle.get("status") in {"resolved", "closed", "settled", "finalized"}:
        return _result("drop", "lifecycle_terminal", 0, 0)
    if lifecycle.get("resolution_date_past") or lifecycle.get("event_date_past"):
        return _result("drop", "lifecycle_past", 0, 0)
    if lifecycle.get("title_date_past") and lifecycle.get("linked_event_past"):
        return _result("drop", "lifecycle_title_and_event_past", 0, 0)

    if row.get("canonical_quality") != "pass":
        return _result("drop", "quality_suppressed", 0, 0)

    match = row.get("match") or {}
    if not match.get("item_id_match"):
        return _result("drop", "item_id_mismatch", 0, 0)
    if not match.get("entity_match"):
        return _result("drop", "entity_mismatch", 0, 0)
    if float(match.get("confidence") or 0) < MATCH_THRESHOLD:
        return _result("drop", "confidence_below_threshold", 0, 0)

    if row.get("stored_age_days", 0) > TTL_DAYS:
        return _result("drop", "boost_expired", 0, 0)
    existing = float(row.get("existing_delta") or 0)
    if row.get("duplicate_pick"):
        delta = max(-CAP, min(CAP, existing))
    else:
        delta = max(-CAP, min(CAP, existing + BOOST))

    if mode == "dry_run":
        return _result("surface", "all_gates_pass", 0, delta)
    if mode != "active" or not row.get("dry_run_approved"):
        return _result("drop", "activation_not_approved", 0, 0)
    return _result("surface", "all_gates_pass", 1, delta)


def _result(verdict: str, reason: str, mutations: int, delta: float) -> dict[str, Any]:
    return {"verdict": verdict, "reason": reason, "mutations": mutations, "effective_delta": delta}


def evaluate_case(row: dict[str, Any]) -> list[str]:
    actual = decide(row)
    expected = row.get("expected") or {}
    errors = [f"{key.upper()}_MISMATCH" for key in ("verdict", "reason", "mutations", "effective_delta") if actual[key] != expected.get(key)]
    if row.get("email_category") != row.get("canonical_category") and row.get("quality_input") != "canonical":
        errors.append("UNTRUSTED_EMAIL_CATEGORY_USED")
    telemetry = row.get("telemetry") or {}
    if any(key in telemetry for key in ("user_id", "email", "token", "query")):
        errors.append("DRY_RUN_PII_LEAK")
    if row.get("mode") == "dry_run" and actual["mutations"]:
        errors.append("DRY_RUN_MUTATED_RANKING")
    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for row in corpus["cases"]:
        actual = evaluate_case(row)
        expected = sorted(row.get("expected_refusals") or [])
        cases.append({"id": row["id"], "ok": actual == expected, "actual": actual})
    return {"total": len(cases), "passed": sum(c["ok"] for c in cases), "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
