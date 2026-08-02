"""Dependency-free evaluator for the C124 calibration main-build contract."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "calibration_main_phase_budget_contract.json"


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
    if payload.get("schema_version") != "calibration-main-phase-budget-contract/v1":
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


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the build lifecycle is honest."""

    errors: list[str] = []
    plan = row["plan"]
    run = row["run"]
    phases = plan["phases"]
    names = [phase.get("name") for phase in phases]
    if len(names) != len(set(names)):
        errors.append("PHASE_DUPLICATE")
    if plan["hard_limit_ms"] <= plan["soft_limit_ms"]:
        errors.append("HARD_LIMIT_NOT_ABOVE_SOFT")
    if plan.get("cleanup_margin_ms", 0) <= 0:
        errors.append("CLEANUP_MARGIN_MISSING")

    declared = 0
    completed_required: set[str] = set()
    for phase in phases:
        budget = phase.get("budget_ms")
        if not phase.get("measured_input"):
            errors.append("PHASE_BUDGET_GUESSED")
        if not isinstance(budget, int) or budget <= 0:
            errors.append("PHASE_BUDGET_MISSING")
            continue
        declared += budget
        timeout = phase.get("statement_timeout_ms")
        if not isinstance(timeout, int) or timeout <= 0 or timeout >= budget:
            errors.append("STATEMENT_TIMEOUT_NOT_INSIDE_PHASE")
        if phase.get("duration_ms", 0) > budget and phase.get("status") == "complete":
            errors.append("PHASE_COMPLETES_OVER_BUDGET")
        if phase.get("required") and phase.get("status") == "complete":
            completed_required.add(phase["name"])
        if phase.get("checkpoint_advanced") and not phase.get("committed"):
            errors.append("CHECKPOINT_BEFORE_COMMIT")
        if phase.get("checkpoint_advanced") and phase.get("checkpoint_write") != "ok":
            errors.append("CHECKPOINT_ADVANCED_AFTER_WRITE_FAILURE")

    if declared + plan.get("cleanup_margin_ms", 0) > plan["soft_limit_ms"]:
        errors.append("DECLARED_BUDGETS_EXHAUST_SOFT_LIMIT")
    if run.get("elapsed_ms", 0) > plan["soft_limit_ms"] and run.get("terminal") == "complete":
        errors.append("COMPLETE_AFTER_SOFT_LIMIT")
    if run.get("unmeasured_overhead_ms", 0) > plan.get("cleanup_margin_ms", 0):
        errors.append("UNMEASURED_OVERHEAD_EXCEEDS_MARGIN")

    required = {phase["name"] for phase in phases if phase.get("required")}
    terminal = run.get("terminal")
    if terminal == "complete":
        if completed_required != required:
            errors.append("COMPLETE_WITH_REQUIRED_PHASE_MISSING")
        if run.get("durable") not in {"ok", "superseded"}:
            errors.append("COMPLETE_WITHOUT_DURABLE")
        if run.get("artifact_generation") is None:
            errors.append("COMPLETE_WITHOUT_GENERATION")
    elif terminal in {"partial", "failed", "cancelled", "hard_loss", "overlap_refused"}:
        if run.get("published"):
            errors.append("INCOMPLETE_RUN_PUBLISHED")
        if run.get("health") == "green":
            errors.append("INCOMPLETE_RUN_GREEN")
    else:
        errors.append("TERMINAL_INVALID")

    if run.get("published") and run.get("durable") not in {"ok", "superseded"}:
        errors.append("PUBLISHED_WITHOUT_DURABLE")
    if run.get("gate") == "refuse" and run.get("published"):
        errors.append("GATE_REFUSAL_PUBLISHED")
    if run.get("volatile") == "ok" and run.get("durable") not in {"ok", "superseded"}:
        errors.append("VOLATILE_AHEAD_OF_DURABLE")
    if terminal == "complete" and run.get("published") is not True:
        errors.append("COMPLETE_NOT_PUBLISHED")
    if terminal != "complete" and run.get("previous_preserved") is not True:
        errors.append("PRIOR_ARTIFACT_NOT_PRESERVED")

    checkpoint = row["checkpoint"]
    if checkpoint.get("version") != run.get("population_version") and checkpoint.get("action") != "invalidate":
        errors.append("CHECKPOINT_VERSION_REUSED")
    if checkpoint.get("owner") != run.get("owner") and checkpoint.get("advanced"):
        errors.append("NON_OWNER_ADVANCES_CHECKPOINT")
    if checkpoint.get("oldest_tail_required") and not checkpoint.get("oldest_tail_reached"):
        errors.append("OLD_TAIL_STARVED")

    cancellation = row.get("cancellation")
    if cancellation:
        if cancellation.get("raised") and not cancellation.get("terminal_recorded"):
            errors.append("CANCELLATION_TERMINAL_MISSING")
        if cancellation.get("swallowed"):
            errors.append("CANCELLATION_SWALLOWED")

    health = row["health"]
    if health.get("artifact_fresh") is False and health.get("verdict") == "green":
        errors.append("STALE_ARTIFACT_GREEN")
    if health.get("artifact_generation") != run.get("artifact_generation") and health.get("verdict") == "green":
        errors.append("HEALTH_GENERATION_MISMATCH")
    if health.get("invocation_success_only") and health.get("verdict") == "green":
        errors.append("INVOCATION_ONLY_GREEN")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if poison.get("healthy_progress_preserved") is not True:
            errors.append("POISON_ERASES_HEALTHY_PROGRESS")

    sequence = row.get("sequence")
    if sequence:
        cursors = sequence.get("cursor_after", [])
        if cursors != sorted(cursors) or len(cursors) != len(set(cursors)):
            errors.append("CURSOR_NOT_MONOTONIC")
        if sequence.get("final_terminal") == "complete" and not sequence.get("final_published"):
            errors.append("SEQUENCE_COMPLETE_NOT_PUBLISHED")

    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for raw in sorted(payload["cases"], key=lambda value: value["id"]):
        row = materialize(payload, raw)
        actual = evaluate_case(row)
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
