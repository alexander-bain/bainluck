"""Dependency-free evaluator for the C116 search latency contract corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "search_latency_budget_contract.json"
ALLOWED_OUTCOMES = {"success", "typed_timeout", "typed_partial"}
ALLOWED_TOTALS = {"exact", "unknown", "bounded"}


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "search-latency-budget-contract/v1":
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


def _result_errors(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    result = row["result"]
    required = row["query"]["required_entity_ids"]
    actual = result["entity_ids"]
    if any(entity not in actual for entity in required):
        errors.append("REQUIRED_RESULT_MISSING")
    expected_top = row["query"].get("expected_top_entity_id")
    if expected_top and (not actual or actual[0] != expected_top):
        errors.append("TOP_RESULT_CHANGED")
    if len(actual) != len(set(actual)):
        errors.append("DUPLICATE_RESULT")
    if result["total_mode"] not in ALLOWED_TOTALS:
        errors.append("TOTAL_MODE_INVALID")
    if result["outcome"] not in ALLOWED_OUTCOMES:
        errors.append("OUTCOME_INVALID")
    return errors


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes. An empty list means the contract passes."""

    errors = _result_errors(row)
    query = row["query"]
    plan = row["plan"]
    result = row["result"]
    stages = plan["stages"]

    if query["league_terms"] and query["remaining_terms"]:
        if plan["event_scope"] != "league_and_remaining_terms":
            errors.append("LEAGUE_TERM_BROADENS_EVENT_SCOPE")
    if plan["count_shape"] != "predicate_identity_only":
        errors.append("COUNT_SHAPE_WIDE")
    if plan["count_has_ordering"]:
        errors.append("COUNT_HAS_ORDERING")
    if plan["count_has_entity_projection"] or plan["count_has_eager_load"]:
        errors.append("COUNT_HAS_UNUSED_WORK")
    if not plan["absolute_deadline_ms"] or plan["absolute_deadline_ms"] <= 0:
        errors.append("ABSOLUTE_DEADLINE_MISSING")
    if not plan["statement_timeout_ms"] or plan["statement_timeout_ms"] >= plan["absolute_deadline_ms"]:
        errors.append("STATEMENT_TIMEOUT_UNBOUNDED")
    if plan["analytics_awaited"]:
        errors.append("ANALYTICS_ON_CRITICAL_PATH")
    if plan["cancellation"] != "propagated":
        errors.append("CANCELLATION_SWALLOWED")

    elapsed = 0
    deadline_crossed_at: dict[str, Any] | None = None
    for stage in stages:
        duration = stage["duration_ms"]
        if not isinstance(duration, int) or duration < 0:
            errors.append("STAGE_DURATION_INVALID")
            continue
        if stage["budget_ms"] is None or stage["budget_ms"] <= 0:
            errors.append("STAGE_BUDGET_MISSING")
        elif duration > stage["budget_ms"] and stage["on_timeout"] == "continue":
            errors.append("STAGE_TIMEOUT_CONTINUES")
        elapsed += duration
        if deadline_crossed_at is None and elapsed > plan["absolute_deadline_ms"]:
            deadline_crossed_at = stage

    if deadline_crossed_at is not None:
        if result["outcome"] == "success":
            errors.append("SUCCESS_AFTER_DEADLINE")
        authority = result["authority_established_before_timeout"]
        if not authority:
            if result["outcome"] != "typed_timeout":
                errors.append("PRE_AUTHORITY_TIMEOUT_NOT_TYPED")
            if result["entity_ids"] or result["total_mode"] != "unknown":
                errors.append("PRE_AUTHORITY_TIMEOUT_FABRICATES_RESULTS")
        else:
            if deadline_crossed_at["essential"]:
                errors.append("ESSENTIAL_STAGE_EXCEEDED_DEADLINE")
            if result["outcome"] != "typed_partial":
                errors.append("POST_AUTHORITY_TIMEOUT_NOT_TYPED_PARTIAL")
            if result["total_mode"] == "bounded" and not result.get("total_bound_reason"):
                errors.append("BOUNDED_TOTAL_UNTYPED")
    elif result["outcome"] != "success":
        errors.append("NON_SUCCESS_WITHIN_BUDGET")

    if row.get("poison"):
        poison = row["poison"]
        if poison["position"] not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if poison["healthy_siblings_survive"] is not True:
            errors.append("POISON_WIPES_HEALTHY_RESULTS")

    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(row)
        expected = sorted(row["expected_errors"])
        details.append({
            "id": row["id"],
            "actual_errors": actual,
            "expected_errors": expected,
            "passed": actual == expected,
        })
    return {
        "schema_version": payload["schema_version"],
        "total": len(details),
        "passed": sum(row["passed"] for row in details),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
