"""Dependency-free evaluator for the C123 search containment and alias corpus."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "search_concept_containment_contract.json"
OUTCOMES = {"found", "miss", "ambiguous"}
SCAFFOLDING = {
    "a", "an", "the", "of", "to", "in", "on", "for", "by", "at", "with",
    "who", "what", "when", "where", "which", "why", "how", "will", "would",
    "is", "are", "be", "does", "do", "did", "can", "could", "should", "vs",
}


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "search-concept-containment-contract/v1":
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


def tokens(value: str) -> list[str]:
    folded = value.casefold().replace("’", "'")
    folded = re.sub(r"'s\b", "s", folded)
    return re.findall(r"[a-z0-9]+", folded)


def meaningful_tokens(value: str) -> set[str]:
    raw = tokens(value)
    kept = {token for token in raw if token not in SCAFFOLDING}
    return kept or set(raw)


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the declared search result is honest."""

    errors: list[str] = []
    query = row["query"]
    oracle = row["oracle"]
    result = row["result"]
    outcome = result.get("outcome")
    if outcome not in OUTCOMES:
        errors.append("OUTCOME_INVALID")

    candidates = result.get("candidates", [])
    identities = [candidate.get("id") for candidate in candidates]
    if len(identities) != len(set(identities)):
        errors.append("DUPLICATE_CANDIDATE")
    if result.get("identity_order") != identities:
        errors.append("IDENTITY_ORDER_MISMATCH")

    query_terms = meaningful_tokens(query)
    for candidate in candidates:
        if candidate.get("surface") == "concept" and candidate.get("query_derived"):
            explained = set(candidate.get("explain_tokens", [])) | set(candidate.get("corroborating_tokens", []))
            if not query_terms <= explained:
                errors.append("CONCEPT_UNEXPLAINED_TERMS")
            if candidate.get("contradictory_terms"):
                errors.append("CONCEPT_CONTRADICTED")

    expected_outcome = oracle["outcome"]
    if outcome != expected_outcome:
        errors.append("OUTCOME_DRIFT")
    expected_top = oracle.get("expected_top")
    actual_top = identities[0] if identities else None
    allowed = set(oracle.get("allowed_top", []))
    if expected_outcome == "found":
        if actual_top != expected_top and actual_top not in allowed:
            errors.append("TOP_IDENTITY_CHANGED")
    elif expected_outcome == "miss":
        if candidates:
            errors.append("MISS_FABRICATES_RESULT")
    elif expected_outcome == "ambiguous":
        if actual_top is not None:
            errors.append("AMBIGUITY_SELECTS_TOP")

    alias = row.get("alias_authority")
    if alias:
        normalized_query = " ".join(tokens(query))
        registered = {" ".join(tokens(value)) for value in alias.get("registered_aliases", [])}
        if normalized_query in registered:
            if actual_top != alias.get("canonical_id"):
                errors.append("REGISTERED_ALIAS_NOT_CANONICAL")
        elif alias.get("ambiguous") and outcome != "ambiguous":
            errors.append("AMBIGUOUS_ALIAS_FORCED")

    if oracle.get("authority") == "none" and actual_top is not None:
        errors.append("IDENTITY_NEEDS_ALEX_RULING")

    response = row.get("response")
    if response:
        counts = response.get("returned_counts", {})
        families = response.get("families", {})
        if set(counts) != set(families):
            errors.append("RESPONSE_FAMILY_SHAPE_DRIFT")
        else:
            for family, values in families.items():
                if counts[family] != len(values):
                    errors.append("RESPONSE_COUNT_FALSE")
        if response.get("total") != sum(counts.values()):
            errors.append("RESPONSE_TOTAL_FALSE")
        if response.get("filters") != oracle.get("filters"):
            errors.append("FILTER_DRIFT")
        if response.get("pagination") != oracle.get("pagination"):
            errors.append("PAGINATION_DRIFT")

    siblings = row.get("siblings")
    if siblings and siblings.get("healthy_survive") is not True:
        errors.append("CONTAINMENT_DROPS_HEALTHY_SIBLINGS")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if poison.get("healthy_survive") is not True:
            errors.append("POISON_WIPES_HEALTHY_CANDIDATES")

    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(row)
        expected = sorted(row["expected_errors"])
        details.append({"id": row["id"], "actual_errors": actual, "expected_errors": expected, "passed": actual == expected})
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
