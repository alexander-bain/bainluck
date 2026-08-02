"""Dependency-free evaluator for the C122 calibration version-rollover corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "calibration_version_rollover_contract.json"
TIERS = {"process", "redis_main", "redis_last_good", "durable"}


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "calibration-version-rollover-contract/v1":
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


def _usable_current(artifact: dict[str, Any], expected: str) -> bool:
    return (
        artifact.get("version") == expected
        and artifact.get("complete") is True
        and artifact.get("valid") is True
        and artifact.get("age") == "inside_serve_bound"
    )


def _usable_previous(artifact: dict[str, Any], previous: str | None, policy: dict[str, Any]) -> bool:
    return (
        previous is not None
        and artifact.get("version") == previous
        and artifact.get("complete") is True
        and artifact.get("valid") is True
        and artifact.get("age") == "inside_rollover_bound"
        and policy.get("previous_compatible") is True
        and policy.get("window") == "explicit_bounded_open"
    )


def _authoritative(artifacts: list[dict[str, Any]], expected: str, previous: str | None, policy: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    current = [a for a in artifacts if _usable_current(a, expected)]
    if current:
        current.sort(key=lambda a: (a["generation"], a["tier"] == "durable"), reverse=True)
        candidate = current[0]
        durable_generations = {a["generation"] for a in current if a["tier"] == "durable"}
        if candidate["tier"] in {"process", "redis_main", "redis_last_good"} and candidate["generation"] not in durable_generations:
            backed = [a for a in current if a["tier"] == "durable"]
            if backed:
                backed.sort(key=lambda a: a["generation"], reverse=True)
                return backed[0], "current"
            return None, "unavailable"
        return candidate, "current"

    prior = [a for a in artifacts if _usable_previous(a, previous, policy)]
    if prior:
        prior.sort(key=lambda a: (a["generation"], a["tier"] == "durable"), reverse=True)
        candidate = prior[0]
        durable_generations = {a["generation"] for a in prior if a["tier"] == "durable"}
        if candidate["tier"] in {"process", "redis_main", "redis_last_good"} and candidate["generation"] not in durable_generations:
            backed = [a for a in prior if a["tier"] == "durable"]
            if not backed:
                return None, "unavailable"
            backed.sort(key=lambda a: a["generation"], reverse=True)
            candidate = backed[0]
        return candidate, "previous_degraded"
    return None, "unavailable"


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes. Empty means the declared rollover is safe."""

    errors: list[str] = []
    expected = row["expected_version"]
    previous = row.get("previous_version")
    policy = row["compatibility"]
    artifacts = row.get("artifacts", [])
    result = row["result"]

    ids = [a.get("id") for a in artifacts]
    if len(ids) != len(set(ids)):
        errors.append("ARTIFACT_ID_DUPLICATE")
    for artifact in artifacts:
        if artifact.get("tier") not in TIERS:
            errors.append("TIER_INVALID")
        if artifact.get("version_relation") not in {"current", "previous", "future", "missing"}:
            errors.append("VERSION_RELATION_INVALID")
        actual_relation = (
            "current" if artifact.get("version") == expected
            else "previous" if previous and artifact.get("version") == previous
            else "missing" if artifact.get("version") is None
            else "future"
        )
        if actual_relation != artifact.get("version_relation"):
            errors.append("VERSION_RELATION_FALSE")

    selected, disposition = _authoritative(artifacts, expected, previous, policy)
    if result.get("selected") != (selected.get("id") if selected else None):
        errors.append("AUTHORITATIVE_SELECTION_FALSE")
    if result.get("disposition") != disposition:
        errors.append("DISPOSITION_FALSE")

    if disposition == "current":
        if result.get("degraded") is not False or result.get("read_only") is not False:
            errors.append("CURRENT_MISLABELLED")
    elif disposition == "previous_degraded":
        if not all((result.get("degraded"), result.get("dated"), result.get("provenance"), result.get("read_only"))):
            errors.append("PREVIOUS_FALLBACK_NOT_EXPLICIT")
        if result.get("may_seed_current") is not False:
            errors.append("PREVIOUS_FALLBACK_SEEDS_CURRENT")
        if policy.get("window") != "explicit_bounded_open":
            errors.append("PREVIOUS_FALLBACK_UNBOUNDED")
    else:
        if result.get("selected") is not None:
            errors.append("UNAVAILABLE_SELECTS_ARTIFACT")

    if result.get("disposition") == "previous_degraded" and policy.get("window") != "explicit_bounded_open":
        errors.append("PREVIOUS_FALLBACK_UNBOUNDED")

    publication = row.get("publication")
    if publication:
        order = publication.get("order", [])
        if "volatile" in order and ("durable" not in order or order.index("volatile") < order.index("durable")):
            errors.append("VOLATILE_BEFORE_DURABLE")
        if publication.get("durable_status") == "error" and publication.get("volatile_status") == "ok":
            errors.append("VOLATILE_PUBLISHED_WITHOUT_DURABLE")
        if publication.get("candidate_complete") is not True and publication.get("published") is True:
            errors.append("INCOMPLETE_CANDIDATE_PUBLISHED")
        if publication.get("gate") == "refuse" and publication.get("published") is True:
            errors.append("GATE_REFUSAL_PUBLISHED")

    transition = row.get("transition")
    if transition:
        if transition.get("population_unit_changed") and not transition.get("alex_ruling"):
            errors.append("POPULATION_UNIT_NEEDS_RULING")
        if transition.get("compatibility_duration") == "guessed":
            errors.append("COMPATIBILITY_DURATION_NEEDS_RULING")
        if transition.get("rollback_reinterprets_incompatible"):
            errors.append("ROLLBACK_REINTERPRETS_BYTES")

    clients = row.get("clients", {})
    for client, state in clients.items():
        if state.get("expected_version") != expected:
            errors.append(f"{client.upper()}_EXPECTED_VERSION_DIVERGES")
        if state.get("accepts_incompatible_as_current"):
            errors.append(f"{client.upper()}_ACCEPTS_INCOMPATIBLE")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if poison.get("healthy_candidates_survive") is not True:
            errors.append("POISON_WIPES_HEALTHY_CANDIDATES")

    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(row)
        expected = sorted(row["expected_errors"])
        details.append({"id": row["id"], "actual_errors": actual, "expected_errors": expected, "passed": actual == expected})
    return {"schema_version": payload["schema_version"], "total": len(details), "passed": sum(d["passed"] for d in details), "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
