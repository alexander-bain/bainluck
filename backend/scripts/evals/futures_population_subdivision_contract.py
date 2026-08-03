"""Dependency-free evaluator for the C126 futures subdivision contract."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "futures_population_subdivision_contract.json"
SCHEMA = "futures-population-subdivision-contract/v1"


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    if not isinstance(payload.get("defaults"), dict):
        raise ValueError("DEFAULTS_REQUIRED")
    return payload


def materialize(payload: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    merged = _merge(payload["defaults"], row)
    merged["id"] = row["id"]
    merged["expected_errors"] = row["expected_errors"]
    return merged


def _by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["observation_id"]): row for row in rows}


def evaluate_case(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    plan = row["plan"]
    monolith = row["monolith"]
    staged = row["staged"]
    lifecycle = row["lifecycle"]

    if plan.get("semantic_change"):
        errors.append("SEMANTIC_CHANGE_NEEDS_ALEX_RULING")
    if plan.get("partition_key") not in {"source", "virtual_question"}:
        errors.append("UNSAFE_PARTITION_KEY")
    if plan.get("cross_chunk_peers") and not plan.get("peers_colocated"):
        errors.append("CROSS_CHUNK_PEER_SPLIT")
    if plan.get("field_members_split"):
        errors.append("FIELD_ROSTER_SPLIT")
    if plan.get("global_finalization") is not True:
        errors.append("GLOBAL_FINALIZATION_MISSING")
    if plan.get("representative_tie") and not plan.get("tie_authority"):
        errors.append("REPRESENTATIVE_TIE_UNSTABLE")
    if plan.get("requires_vacuum_or_index_for_correctness"):
        errors.append("PHYSICAL_REPAIR_REQUIRED_FOR_CORRECTNESS")

    mono_rows = _by_id(monolith.get("observations", []))
    staged_rows = _by_id(staged.get("observations", []))
    if set(mono_rows) != set(staged_rows):
        errors.append("OBSERVATION_IDENTITY_DRIFT")
    if len(monolith.get("observations", [])) != len(staged.get("observations", [])):
        errors.append("OBSERVATION_COUNT_DRIFT")
    for obs_id in sorted(set(mono_rows) & set(staged_rows)):
        left, right = mono_rows[obs_id], staged_rows[obs_id]
        if left.get("representative") != right.get("representative"):
            errors.append("REPRESENTATIVE_DRIFT")
        if left.get("probability") != right.get("probability"):
            errors.append("NORMALIZED_PROBABILITY_DRIFT")
        if left.get("cohort") != right.get("cohort"):
            errors.append("COHORT_LABEL_DRIFT")
        if left.get("bucket") != right.get("bucket"):
            errors.append("BUCKET_DRIFT")
        if left.get("winner") != right.get("winner"):
            errors.append("TRUTH_DRIFT")
    if monolith.get("census") != staged.get("census"):
        errors.append("CENSUS_DRIFT")

    generation = lifecycle.get("generation")
    if not generation or generation != lifecycle.get("finalize_generation"):
        errors.append("INPUT_GENERATION_MISMATCH")
    if lifecycle.get("population_version") != lifecycle.get("checkpoint_version"):
        if lifecycle.get("checkpoint_action") != "invalidate":
            errors.append("STALE_CHECKPOINT_REUSED")
    if lifecycle.get("checkpoint_advanced") and not lifecycle.get("committed"):
        errors.append("CHECKPOINT_BEFORE_COMMIT")
    if lifecycle.get("checkpoint_owner") != lifecycle.get("run_owner") and lifecycle.get("checkpoint_advanced"):
        errors.append("NON_OWNER_ADVANCES_CHECKPOINT")
    if lifecycle.get("partial") and lifecycle.get("published"):
        errors.append("PARTIAL_GENERATION_PUBLISHED")
    if lifecycle.get("partial") and lifecycle.get("health") == "green":
        errors.append("PARTIAL_GENERATION_GREEN")
    if lifecycle.get("published") and lifecycle.get("durable") != "ok":
        errors.append("PUBLISHED_BEFORE_DURABLE")
    if lifecycle.get("retry") and not lifecycle.get("idempotent"):
        errors.append("RETRY_NOT_IDEMPOTENT")
    if lifecycle.get("late_arrival") and not lifecycle.get("generation_invalidated"):
        errors.append("LATE_ARRIVAL_NOT_INVALIDATED")
    if lifecycle.get("deploy_overlap") and not lifecycle.get("old_new_isolated"):
        errors.append("DEPLOY_GENERATIONS_MIXED")
    if lifecycle.get("cancelled") and not lifecycle.get("terminal_recorded"):
        errors.append("CANCELLATION_TERMINAL_MISSING")
    if lifecycle.get("cleanup_deleted_authoritative"):
        errors.append("CLEANUP_DELETED_AUTHORITATIVE_GENERATION")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if not poison.get("siblings_preserved"):
            errors.append("POISON_ERASES_SIBLINGS")
    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for raw in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(materialize(payload, raw))
        expected = sorted(raw["expected_errors"])
        details.append({"id": raw["id"], "actual_errors": actual, "expected_errors": expected, "passed": actual == expected})
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
