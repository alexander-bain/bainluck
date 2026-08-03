"""Dependency-free C139 contract for tournament UX inventory and issue closure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "tournament-ux-closure-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "tournament_ux_closure_contract.json"


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


def classify_surface(row: dict[str, Any]) -> str:
    required = set(row.get("required") or [])
    present = set(row.get("static_present") or [])
    if row.get("runtime_broken") or row.get("wrong_domain_adapter") or row.get("partial_decode_blanks"):
        return "BROKEN"
    if row.get("domain_specific_required") and not row.get("domain_adapter"):
        return "UNSTARTED" if not (required & present) else "SHIPPED_PARTIAL"
    missing = required - present
    if missing:
        return "UNSTARTED" if not present else "SHIPPED_PARTIAL"
    evidence = row.get("rendered_evidence") or {}
    if not (
        evidence.get("desktop")
        and evidence.get("mobile")
        and evidence.get("deployed_sha")
        and evidence.get("screenshots")
        and evidence.get("trace")
        and evidence.get("console_network_checked")
        and evidence.get("adjacent_regression")
    ):
        return "SHIPPED_PARTIAL"
    return "SHIPPED_GOOD"


def evaluate_case(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = row.get("kind", "surface")
    if kind == "surface":
        actual = classify_surface(row)
        if actual != row.get("expected_status"):
            errors.append("SURFACE_STATUS_MISMATCH")
        if row.get("claimed_closed") and actual != "SHIPPED_GOOD":
            errors.append("PREMATURE_CHILD_CLOSURE")
    elif kind == "parent_closure":
        children = row.get("child_statuses") or []
        actual_closed = bool(children) and all(x == "SHIPPED_GOOD" for x in children)
        if actual_closed != row.get("expected_closed"):
            errors.append("PARENT_CLOSURE_MISMATCH")
        if row.get("claimed_closed") and not actual_closed:
            errors.append("PREMATURE_PARENT_CLOSURE")
    elif kind == "promotion":
        released = row.get("latency_status") == "green" or row.get("alex_release") is True
        actual = row.get("candidate") if released and row.get("candidate_unblocked") else None
        if actual != row.get("expected_promoted"):
            errors.append("PROMOTION_ORDER_MISMATCH")
    else:
        errors.append("CASE_KIND_INVALID")
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
