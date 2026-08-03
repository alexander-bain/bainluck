"""Dependency-free C129 contract for Discover cold-build ownership and truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "cold-feed-generation-contract/v1"
FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "cold_feed_generation_contract.json"
)

REQUIRED_PHASE_FIELDS = {
    "name",
    "owner",
    "hard_budget_ms",
    "generation",
    "cache_scope",
    "terminal_state",
}


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


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the described flow is safe."""
    errors: list[str] = []
    phases = row.get("phases") or []
    for phase in phases:
        if not REQUIRED_PHASE_FIELDS <= set(phase):
            errors.append("PHASE_CONTRACT_INCOMPLETE")
            continue
        budget = phase.get("hard_budget_ms")
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            errors.append("PHASE_BUDGET_UNBOUNDED")

    builds: dict[tuple[str, str], set[str]] = {}
    for event in row.get("events") or []:
        kind = event.get("kind")
        key = (str(event.get("base_identity")), str(event.get("generation")))
        owner = str(event.get("owner"))
        if kind == "candidate_build_start":
            builds.setdefault(key, set()).add(owner)
        if kind == "publish":
            if event.get("quality") != "complete":
                errors.append("INCOMPLETE_BUILD_PUBLISHED")
            if event.get("owner_state") in {"cancelled", "failed", "hard_lost"}:
                errors.append("DEAD_OWNER_PUBLISHED")
            if event.get("generation") != row.get("generation"):
                errors.append("MIXED_GENERATION_PUBLISH")
        if kind == "terminal" and event.get("state") in {"cancelled", "failed"}:
            if event.get("slot_state") != "released":
                errors.append("DEAD_OWNER_STRANDED_SLOT")

    if any(len(owners) > 1 for owners in builds.values()):
        errors.append("DUPLICATE_CANDIDATE_BUILD_OWNER")

    response = row.get("response") or {}
    if response.get("availability") == "unavailable":
        if response.get("items") == [] and not response.get("typed_unavailable"):
            errors.append("UNAVAILABLE_MASQUERADES_AS_EMPTY")
        if response.get("typed_unavailable") and not response.get(
            "client_consumes_unavailable", True
        ):
            errors.append("CLIENT_DROPS_UNAVAILABLE_STATE")
    if response.get("quality") == "degraded" and response.get("replaced_last_good"):
        errors.append("DEGRADED_REPLACED_LAST_GOOD")
    if response.get("candidate_ids") != response.get("warm_path_candidate_ids"):
        errors.append("CANDIDATE_IDENTITY_OR_ORDER_DRIFT")
    if response.get("payload_version") == "old" and response.get("rendered_zero"):
        errors.append("OLD_PAYLOAD_MISSING_BECAME_ZERO")
    if row.get("waiter_started_duplicate"):
        errors.append("WAITER_BECAME_BUILD_OWNER")

    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    results = []
    for case in corpus["cases"]:
        actual = evaluate_case(case)
        expected = sorted(case.get("expected_refusals") or [])
        results.append({"id": case["id"], "ok": actual == expected, "actual": actual})
    return {
        "total": len(results),
        "passed": sum(row["ok"] for row in results),
        "cases": results,
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
