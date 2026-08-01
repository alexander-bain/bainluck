"""Pure C118 checkpoint, publication, and health contract evaluator."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "calibration_task_resumability_contract.json"


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else copy.deepcopy(value)
    return out


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if payload.get("schema_version") != "calibration-task-resumability/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    defaults, cases = payload.get("defaults"), payload.get("cases")
    if not isinstance(defaults, dict) or not isinstance(cases, list):
        raise ValueError("CORPUS_INVALID")
    ids = [row.get("id") for row in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    payload["cases"] = [_merge(defaults[row["task"]], row) for row in cases]
    return payload


def evaluate_case(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cp, chunk, tx, output, health = row["checkpoint"], row["chunk"], row["transaction"], row["output"], row["health"]
    if row["ordering"] != "stable_oldest_first": errors.append("UNSTABLE_OR_STARVING_ORDER")
    if row["checkpoint_version"] != row["population_version"] and row["version_action"] != "invalidate": errors.append("STALE_CHECKPOINT_REUSED")
    if row["ownership"] != "acquired" and (tx["committed"] or output["published"]): errors.append("NON_OWNER_MUTATED")
    if not tx["committed"] and cp["next"] != cp["before"]: errors.append("CHECKPOINT_AHEAD_OF_COMMIT")
    if tx["committed"] and cp["next"] != chunk["end"]: errors.append("CHECKPOINT_NOT_AT_COMMITTED_END")
    if tx["committed"] and tx["rows_committed"] + tx["rows_failed"] > tx["rows_attempted"]: errors.append("ROW_LEDGER_INVALID")
    if row["duplicate_delivery"] and not row["idempotent"]: errors.append("DUPLICATE_NOT_IDEMPOTENT")
    if row["poison_position"] and not row["healthy_siblings_survive"]: errors.append("POISON_WIPES_SIBLINGS")
    complete = output["all_phases_complete"] and output["durable_generation_committed"] and row["interruption"] == "none"
    if output["published"] and not complete: errors.append("PARTIAL_OUTPUT_PUBLISHED")
    if output["complete"] != complete: errors.append("COMPLETENESS_FALSE_CLAIM")
    if health["verdict"] == "GREEN" and (not complete or not health["terminal_event_retained"] or health["checked"] == 0): errors.append("FALSE_GREEN")
    if not health["metrics_available"] and health["verdict"] != "UNKNOWN": errors.append("METRIC_LOSS_NOT_UNKNOWN")
    if row["interruption"] in {"cancel_before_commit", "soft_before_commit", "hard_loss"} and tx["committed"]: errors.append("PRECOMMIT_INTERRUPTION_COMMITTED")
    if row["old_tail_reachable"] is not True: errors.append("OLD_TAIL_STARVED")
    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda x: x["id"]):
        actual = evaluate_case(row)
        expected = sorted(row["expected_errors"])
        details.append({"id": row["id"], "passed": actual == expected, "actual": actual, "expected": expected})
    return {"total": len(details), "passed": sum(x["passed"] for x in details), "details": details}


def main() -> int:
    report = evaluate_corpus(load_corpus())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__": raise SystemExit(main())
