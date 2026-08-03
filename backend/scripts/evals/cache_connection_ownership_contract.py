"""Dependency-free evaluator for the C125 cache connection ownership contract."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "cache_connection_ownership_contract.json"
SCHEMA = "cache-connection-ownership-contract/v1"


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


def evaluate_case(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    capacity = row.get("plan_capacity")
    headroom = row.get("required_headroom", 0)
    clients = row.get("clients", [])
    if not isinstance(capacity, int) or capacity <= 0:
        errors.append("PLAN_CAPACITY_UNKNOWN")
    if not isinstance(headroom, int) or headroom < 0:
        errors.append("HEADROOM_INVALID")
        headroom = 0
    if not clients:
        errors.append("CLIENT_INVENTORY_EMPTY")

    demand = 0
    identities: set[tuple[str, str]] = set()
    for client in clients:
        process = client.get("process")
        pool_id = client.get("pool_id")
        identity = (str(process), str(pool_id))
        if identity in identities:
            errors.append("POOL_ID_DUPLICATE_IN_PROCESS")
        identities.add(identity)
        maximum = client.get("max_connections")
        instances = client.get("instances")
        if not isinstance(maximum, int) or maximum <= 0:
            errors.append("POOL_MAX_UNBOUNDED")
        elif not isinstance(instances, int) or instances <= 0:
            errors.append("POOL_INSTANCE_COUNT_UNKNOWN")
        else:
            demand += maximum * instances
        if not client.get("owner"):
            errors.append("POOL_OWNER_MISSING")
        if client.get("lifetime") not in {"process", "task", "operation"}:
            errors.append("POOL_LIFETIME_UNBOUNDED")
        if client.get("construction") in {"per_request", "per_market", "per_call"}:
            errors.append("POOL_CONSTRUCTION_MULTIPLIES")
        if client.get("lifetime") in {"task", "operation"}:
            required = {"normal", "exception", "cancellation"}
            if not required <= set(client.get("close_paths", [])):
                errors.append("POOL_CLOSE_PATH_INCOMPLETE")
        if client.get("hard_loss") not in {"process_reap", "provider_reap"}:
            errors.append("HARD_LOSS_OWNERSHIP_UNKNOWN")
        if client.get("retry_creates_pool") or not client.get("retry_same_budget", False):
            errors.append("RETRY_ESCAPES_POOL_BUDGET")
        if client.get("sync_on_event_loop"):
            errors.append("SYNC_RETRY_BLOCKS_EVENT_LOOP")

    if isinstance(capacity, int) and capacity > 0 and demand + headroom > capacity:
        errors.append("CONSERVATIVE_DEMAND_EXCEEDS_PLAN")

    incident = row.get("incident", {})
    if incident.get("cancelled") and not incident.get("released_or_invalidated"):
        errors.append("CANCELLATION_LEAKS_CONNECTION")
    if incident.get("exception") and not incident.get("released_or_invalidated"):
        errors.append("EXCEPTION_LEAKS_CONNECTION")
    if incident.get("double_close_corrupts"):
        errors.append("DOUBLE_CLOSE_CORRUPTS_POOL")
    if incident.get("pool_exhausted") and incident.get("verdict") == "green":
        errors.append("POOL_EXHAUSTION_GREEN")
    if incident.get("tls_eof") and incident.get("retry_unbounded"):
        errors.append("TLS_RETRY_UNBOUNDED")

    migration = row.get("migration", {})
    if migration.get("deploy_overlap") and not migration.get("old_new_budgeted_together"):
        errors.append("DEPLOY_OVERLAP_UNBUDGETED")
    if migration.get("fork") and not migration.get("post_fork_pool"):
        errors.append("INHERITED_SOCKET_REUSED_AFTER_FORK")
    if migration.get("provider_failover") and migration.get("stale_socket_reused"):
        errors.append("STALE_SOCKET_REUSED_AFTER_FAILOVER")
    if migration.get("resize_required_for_correctness"):
        errors.append("RESIZE_REQUIRED_FOR_CORRECTNESS")

    fallback = row.get("fallback", {})
    if fallback.get("redis_down"):
        if fallback.get("durable_authority") != "postgresql":
            errors.append("CACHE_BECOMES_DURABLE_AUTHORITY")
        if fallback.get("verdict") in {"green", "no_data"}:
            errors.append("CACHE_FAILURE_FALSE_GREEN_OR_NO_DATA")
        if not fallback.get("bounded"):
            errors.append("CACHE_FAILURE_UNBOUNDED")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if not poison.get("siblings_preserved"):
            errors.append("POISON_ERASES_SIBLING_CLIENTS")
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
