"""Pure evaluator for C117 durable calibration and sentinel state contracts."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "durable_state_survival_contract.json"
READ_STATES = {"ok", "missing", "unavailable", "tls_eof", "timeout", "malformed", "wrong_type"}
SOURCES = {"volatile", "durable", "process", "unavailable"}


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "durable-state-survival/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases]
    if any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    defaults = payload.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("DEFAULTS_REQUIRED")

    def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    payload["cases"] = [merge(defaults, row) for row in cases]
    return payload


def _valid(read: dict[str, Any], artifact: dict[str, Any]) -> bool:
    return (
        read["state"] == "ok"
        and read["schema_version"] == artifact["schema_version"]
        and read["checksum_valid"] is True
        and read["complete"] is True
        and 0 <= read["age_s"] <= artifact["max_age_s"]
    )


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    artifact = row["artifact"]
    reads = row["reads"]
    publication = row["publication"]
    errors: list[str] = []

    for name in ("volatile", "durable", "process"):
        if reads[name]["state"] not in READ_STATES:
            errors.append(f"{name.upper()}_STATE_INVALID")

    volatile_ok = _valid(reads["volatile"], artifact)
    durable_ok = _valid(reads["durable"], artifact)
    process_ok = _valid(reads["process"], artifact) and not reads["fresh_process"]

    if volatile_ok and durable_ok and reads["volatile"]["generation"] > reads["durable"]["generation"]:
        errors.append("VOLATILE_AHEAD_OF_DURABLE")
        source = "durable"
    elif durable_ok and (not volatile_ok or reads["durable"]["generation"] > reads["volatile"]["generation"]):
        source = "durable"
    elif volatile_ok:
        source = "volatile"
    elif durable_ok:
        source = "durable"
    elif process_ok:
        source = "process"
    else:
        source = "unavailable"

    if reads["fresh_process"] and source == "process":
        errors.append("FRESH_PROCESS_USES_PROCESS_MEMORY")
        source = "unavailable"

    task_success: bool | None
    if publication["stage"] == "not_applicable":
        task_success = None
    else:
        task_success = (
            publication["compute_complete"]
            and publication["durable_write"] == "ok"
            and not publication["cancelled"]
            and "VOLATILE_AHEAD_OF_DURABLE" not in errors
        )
        if not publication["compute_complete"] and publication["durable_write"] != "not_attempted":
            errors.append("INCOMPLETE_COMPUTE_WRITES_DURABLE")
        if publication["durable_write"] != "ok" and publication["volatile_write"] == "ok":
            errors.append("VOLATILE_PUBLISHED_WITHOUT_DURABLE")
        if publication["cancelled"] and publication["volatile_write"] != "not_attempted":
            errors.append("CANCELLED_RUN_PUBLISHED")
        if publication["prior_last_good_preserved"] is not True:
            errors.append("PRIOR_LAST_GOOD_DESTROYED")

    if source == "unavailable" or artifact["checked"] == 0 or errors:
        health = "UNKNOWN"
    else:
        health = artifact["payload_verdict"]

    provenance = {
        "source": source,
        "dated": source in {"durable", "process"},
        "schema_version": None if source == "unavailable" else artifact["schema_version"],
        "generation": None if source == "unavailable" else reads[source]["generation"],
        "complete": source != "unavailable",
    }
    surfaces = {name: {"source": source, "health": health} for name in row["surfaces"]}

    if row.get("composite"):
        if not row["composite"].get("per_field_metadata"):
            errors.append("MIXED_COMPOSITE_ERASES_PROVENANCE")
            health = "UNKNOWN"
        if row["composite"].get("checked_zero_as_green"):
            errors.append("CHECKED_ZERO_GREEN")
            health = "UNKNOWN"

    if row.get("poison") and row["poison"].get("healthy_siblings_survive") is not True:
        errors.append("POISON_WIPES_HEALTHY_STATE")
        health = "UNKNOWN"

    return {
        "provenance": provenance,
        "health": health,
        "task_success": task_success,
        "surfaces": surfaces,
        "errors": sorted(set(errors)),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(row)
        expected = row["expected"]
        oracle_actual = {
            "source": actual["provenance"]["source"],
            "health": actual["health"],
            "task_success": actual["task_success"],
            "errors": actual["errors"],
        }
        details.append({"id": row["id"], "passed": oracle_actual == expected, "actual": oracle_actual, "expected": expected})
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
