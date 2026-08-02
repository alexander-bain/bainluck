"""Dependency-free evaluator for the C121 search response truth corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "search_response_truth_contract.json"
FAMILIES = ("concepts", "teams", "events", "futures")
OUTCOMES = {"success", "typed_partial", "typed_timeout", "cancelled"}
TOTAL_MODES = {"exact", "bounded", "unknown"}


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "search-response-truth-contract/v1":
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


def _identities(response: dict[str, Any]) -> list[str]:
    return [identity for family in FAMILIES for identity in response["families"][family]]


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; an empty list means the case satisfies the contract."""

    errors: list[str] = []
    response = row["response"]
    outcome = response.get("outcome")
    if outcome not in OUTCOMES:
        errors.append("OUTCOME_INVALID")

    families = response.get("families", {})
    counts = response.get("returned_counts", {})
    if set(families) != set(FAMILIES) or set(counts) != set(FAMILIES):
        errors.append("FAMILY_SHAPE_INCOMPLETE")
    else:
        for family in FAMILIES:
            if counts[family] != len(families[family]):
                errors.append("RETURNED_COUNT_MISMATCH")

    identities = _identities(response) if set(families) == set(FAMILIES) else []
    if len(identities) != len(set(identities)):
        errors.append("DUPLICATE_IDENTITY")
    if response.get("identity_order") != identities:
        errors.append("IDENTITY_ORDER_MISMATCH")

    total = response.get("total", {})
    mode = total.get("mode")
    scope = total.get("scope")
    field = total.get("field")
    value = total.get("value")
    if mode not in TOTAL_MODES:
        errors.append("TOTAL_MODE_INVALID")
    if scope not in {"all_families", "events_only"}:
        errors.append("TOTAL_SCOPE_INVALID")
    if scope == "events_only" and field != "event_total_results":
        errors.append("EVENT_TOTAL_FIELD_AMBIGUOUS")
    if scope == "all_families" and field != "total_results":
        errors.append("ALL_TOTAL_FIELD_AMBIGUOUS")
    if mode == "exact":
        expected = sum(counts.values()) if scope == "all_families" else counts.get("events")
        if value != expected:
            errors.append("EXACT_TOTAL_FALSE")
    elif value is not None:
        errors.append("NONEXACT_TOTAL_HAS_VALUE")
    if mode == "bounded" and not total.get("bound_reason"):
        errors.append("BOUNDED_TOTAL_REASON_MISSING")

    complete = response.get("complete")
    omitted = response.get("omitted_families", [])
    if outcome == "success":
        if complete is not True or omitted:
            errors.append("SUCCESS_NOT_COMPLETE")
        if mode != "exact":
            errors.append("SUCCESS_TOTAL_NOT_EXACT")
    elif outcome == "typed_timeout":
        if response.get("authority_established") is not False:
            errors.append("PRE_AUTHORITY_TIMEOUT_MISSTATED")
        if identities or mode != "unknown" or complete is not False:
            errors.append("PRE_AUTHORITY_TIMEOUT_FABRICATES_TRUTH")
    elif outcome == "typed_partial":
        if response.get("authority_established") is not True:
            errors.append("PARTIAL_WITHOUT_AUTHORITY")
        if complete is not False or not omitted:
            errors.append("PARTIAL_OMISSION_UNDECLARED")
        if mode == "exact" and omitted:
            errors.append("PARTIAL_TOTAL_CLAIMS_EXACT")
    elif outcome == "cancelled":
        if identities or mode != "unknown" or complete is not False:
            errors.append("CANCELLATION_RETURNS_SEARCH_TRUTH")

    oracle = row["oracle"]
    expected_ids = oracle["identity_order"]
    required = oracle.get("required_identity_ids", [])
    if any(identity not in identities for identity in required):
        errors.append("REQUIRED_IDENTITY_MISSING")
    if outcome in {"success", "typed_partial"} and response.get("authority_established"):
        if identities != expected_ids:
            errors.append("IDENTITY_DRIFT")
        expected_top = oracle.get("top_identity")
        actual_top = identities[0] if identities else None
        if actual_top != expected_top:
            errors.append("TOP_IDENTITY_CHANGED")
        if response.get("filters") != oracle.get("filters"):
            errors.append("FILTER_DRIFT")
        if response.get("pagination") != oracle.get("pagination"):
            errors.append("PAGINATION_DRIFT")

    repair = row.get("repair")
    if repair:
        allowed = {
            "contained_league_predicate", "predicate_only_count", "bounded_deadlines",
            "optional_enrichment_cutoff", "analytics_off_path",
        }
        if repair.get("stage") not in allowed:
            errors.append("REPAIR_STAGE_INVALID")
        if repair.get("semantic_change"):
            errors.append("SEMANTIC_CHANGE_NEEDS_RULING")

    enrichment = response.get("enrichment", {})
    if enrichment.get("state") == "stale" and enrichment.get("changes_identity"):
        errors.append("STALE_ENRICHMENT_CHANGES_IDENTITY")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if poison.get("healthy_siblings_survive") is not True:
            errors.append("POISON_WIPES_HEALTHY_RESULTS")

    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(row)
        expected = sorted(row["expected_errors"])
        details.append({"id": row["id"], "actual_errors": actual, "expected_errors": expected, "passed": actual == expected})
    return {
        "schema_version": payload["schema_version"],
        "total": len(details),
        "passed": sum(item["passed"] for item in details),
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
