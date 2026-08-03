"""Dependency-free C133 contract for safely sharing anonymous cold-feed work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "anonymous-cold-sharing-contract/v1"
FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "anonymous_cold_sharing_contract.json"
)

SHAPE_FIELDS = {"mode", "sport", "static_tags", "limit", "offset"}


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)):
        raise ValueError("CASE_IDS_INVALID")
    return payload


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the sharing flow is safe."""
    errors: list[str] = []
    artifact = row.get("artifact") or {}
    request = row.get("request") or {}
    response = row.get("response") or {}
    artifact_type = artifact.get("type")

    if artifact.get("owner_count", 1) > 1:
        errors.append("DUPLICATE_SHARED_BUILD_OWNER")
    if artifact.get("quality") != "complete" and artifact.get("published"):
        errors.append("DEGRADED_ARTIFACT_PUBLISHED")
    if artifact.get("generation") != request.get("generation") and response.get("applied"):
        errors.append("STALE_GENERATION_APPLIED")
    if artifact.get("contains_principal_data") and artifact.get("producer_principal") != request.get("principal"):
        errors.append("CROSS_PRINCIPAL_ARTIFACT")

    artifact_shape = artifact.get("shape") or {}
    request_shape = request.get("shape") or {}
    if artifact_type == "response":
        if not SHAPE_FIELDS <= set(artifact_shape) or any(
            artifact_shape.get(field) != request_shape.get(field) for field in SHAPE_FIELDS
        ):
            errors.append("WRONG_RESPONSE_SHAPE")
        if artifact.get("producer_principal") != request.get("principal"):
            errors.append("CROSS_PRINCIPAL_RESPONSE")
    elif artifact_type in {"candidate_base", "shared_intermediate"}:
        for field in ("mode", "sport", "static_tags"):
            if artifact_shape.get(field) != request_shape.get(field):
                errors.append("WRONG_SHARED_BASE_IDENTITY")
                break

    authority = request.get("interaction_authority")
    if artifact_type != "candidate_base" and authority not in {"known_zero", "known_present"}:
        errors.append("INTERACTION_AUTHORITY_UNKNOWN")
    if artifact_type == "shared_intermediate" and not response.get("request_filters_reapplied"):
        errors.append("REQUEST_FILTERS_NOT_REAPPLIED")

    response_ids = response.get("ids") or []
    expected_ids = response.get("expected_ids") or []
    if response_ids != expected_ids:
        errors.append("RESPONSE_IDENTITY_OR_ORDER_DRIFT")
    forbidden = set(request.get("seen_ids") or []) | set(request.get("dismissed_ids") or [])
    if forbidden & set(response_ids):
        errors.append("SEEN_OR_DISMISSED_CARD_RESURRECTED")

    fallback = row.get("fallback") or {}
    if fallback:
        if fallback.get("tier") not in {"fresh", "stale", "last_good", "unavailable"}:
            errors.append("UNSAFE_FALLBACK_TIER")
        if fallback.get("expired") or fallback.get("malformed"):
            errors.append("UNSAFE_FALLBACK_ARTIFACT")
        if fallback.get("identity") != fallback.get("required_identity"):
            errors.append("FALLBACK_IDENTITY_MISMATCH")
        if fallback.get("replaced_last_good") and artifact.get("quality") != "complete":
            errors.append("DEGRADED_REPLACED_LAST_GOOD")

    invariants = row.get("invariants") or {}
    if invariants and any(
        invariants.get(field) is not True
        for field in ("ranking", "counts", "freshness", "complete_only")
    ):
        errors.append("SHARING_SEMANTICS_DRIFT")

    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for row in corpus["cases"]:
        actual = evaluate_case(row)
        expected = sorted(row.get("expected_refusals") or [])
        cases.append({"id": row["id"], "ok": actual == expected, "actual": actual})
    return {
        "total": len(cases),
        "passed": sum(case["ok"] for case in cases),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
