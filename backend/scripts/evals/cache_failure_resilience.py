"""Offline cache-failure resilience contract for feed and calibration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "cache-failure-resilience/v1"
ENDPOINTS = {"feed", "calibration"}


def _finding(code: str, scenario_id: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "scenario_id": scenario_id, "path": path, "message": message}


def evaluate_scenario(
    scenario: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Return deterministic contract violations for one synthetic fault scenario."""

    sid = str(scenario.get("id") or "__missing__")
    findings: list[dict[str, str]] = []
    if scenario.get("endpoint") not in ENDPOINTS:
        findings.append(
            _finding(
                "ENDPOINT_INVALID", sid, "endpoint", "feed or calibration required"
            )
        )

    op_deadline = policy["redis_operation_deadline_ms"]
    router_timeout = policy["router_timeout_ms"]
    compute_deadline = policy["compute_deadline_ms"]

    for index, stage in enumerate(scenario.get("redis_stages") or []):
        path = f"redis_stages[{index}]"
        if stage.get("event_loop_blocked"):
            findings.append(
                _finding(
                    "EVENT_LOOP_BLOCKED", sid, path, "Redis work blocked the async loop"
                )
            )
        if stage.get("duration_ms", 0) > op_deadline and stage.get("awaited", True):
            findings.append(
                _finding(
                    "REDIS_OPERATION_OVER_DEADLINE",
                    sid,
                    path,
                    "Redis operation exceeded supplied deadline",
                )
            )
        if stage.get("client_closed") is not True:
            findings.append(
                _finding(
                    "CLIENT_NOT_CLOSED",
                    sid,
                    path,
                    "Redis client/pool ownership was lost",
                )
            )

    last_good = scenario.get("last_good") or {}
    compute = scenario.get("compute") or {}
    if (
        last_good.get("available")
        and last_good.get("usable")
        and compute.get("started")
    ):
        findings.append(
            _finding(
                "COLD_COMPUTE_WITH_LAST_GOOD",
                sid,
                "compute",
                "usable last-good must serve before cold work",
            )
        )
    if compute.get("duration_ms", 0) > compute.get("deadline_ms", compute_deadline):
        findings.append(
            _finding(
                "COMPUTE_DEADLINE_EXCEEDED",
                sid,
                "compute.duration_ms",
                "compute exceeded supplied deadline",
            )
        )
    if (
        compute.get("passes", 1) > 1
        and compute.get("duration_ms", 0) > compute_deadline
    ):
        findings.append(
            _finding(
                "REPEATED_COMPUTE_OVER_BUDGET",
                sid,
                "compute.passes",
                "repeat pass exceeded total compute policy",
            )
        )

    requests = int(scenario.get("concurrent_requests") or 1)
    builds = int(scenario.get("builds_started") or 0)
    if requests > 1 and builds > 1:
        findings.append(
            _finding(
                "BUILD_STAMPEDE",
                sid,
                "builds_started",
                "identical concurrent requests started multiple builds",
            )
        )

    db = scenario.get("db") or {}
    if (
        db.get("checkout_result") == "timeout"
        or db.get("wait_ms", 0) > policy["db_checkout_deadline_ms"]
    ):
        findings.append(
            _finding(
                "DB_CHECKOUT_OVER_DEADLINE",
                sid,
                "db",
                "DB checkout exceeded supplied deadline",
            )
        )

    write = scenario.get("cache_write") or {}
    if (
        write.get("awaited_before_response")
        and write.get("duration_ms", 0) > op_deadline
    ):
        findings.append(
            _finding(
                "CACHE_WRITE_BLOCKED_RESPONSE",
                sid,
                "cache_write",
                "cache publication delayed a ready response",
            )
        )

    response = scenario.get("response") or {}
    if response.get("elapsed_ms", 0) >= router_timeout:
        findings.append(
            _finding(
                "ROUTER_BUDGET_EXCEEDED",
                sid,
                "response.elapsed_ms",
                "response reached external router cutoff",
            )
        )
    if scenario.get("cache_state") == "malformed" and not scenario.get(
        "typed_cache_error"
    ):
        findings.append(
            _finding(
                "MALFORMED_CACHE_UNTYPED",
                sid,
                "cache_state",
                "malformed cache needs a typed fallback outcome",
            )
        )

    metrics = scenario.get("metrics") or {}
    unhealthy = bool(findings) or response.get("kind") in {
        "error",
        "timeout",
        "degraded",
    }
    if unhealthy and (
        not metrics.get("independent") or metrics.get("verdict") == "green"
    ):
        findings.append(
            _finding(
                "OBSERVABILITY_FALSE_GREEN",
                sid,
                "metrics",
                "failure lacks independent non-green evidence",
            )
        )

    findings.sort(key=lambda row: (row["path"], row["code"]))
    return {
        "id": sid,
        "valid": not findings,
        "codes": sorted({row["code"] for row in findings}),
        "findings": findings,
    }


def evaluate_pack(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            _finding(
                "SCHEMA_VERSION_INVALID",
                "__pack__",
                "schema_version",
                f"expected {SCHEMA_VERSION}",
            )
        )
    policy = payload.get("policy") or {}
    required = (
        "version",
        "router_timeout_ms",
        "redis_operation_deadline_ms",
        "compute_deadline_ms",
        "db_checkout_deadline_ms",
    )
    if any(policy.get(key) is None for key in required):
        errors.append(
            _finding(
                "POLICY_INVALID",
                "__pack__",
                "policy",
                "versioned deadline policy is required",
            )
        )
        return {
            "valid": False,
            "results": [],
            "named_blockers": [],
            "failure_counts": {},
            "errors": errors,
        }
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        errors.append(
            _finding(
                "SCENARIOS_MISSING",
                "__pack__",
                "scenarios",
                "nonempty scenario list required",
            )
        )
        return {
            "valid": False,
            "results": [],
            "named_blockers": [],
            "failure_counts": {},
            "errors": errors,
        }

    seen: set[str] = set()
    results = []
    for scenario in scenarios:
        sid = scenario.get("id")
        if not sid or sid in seen:
            errors.append(
                _finding(
                    "SCENARIO_ID_INVALID", str(sid), "id", "scenario IDs must be unique"
                )
            )
            continue
        seen.add(sid)
        results.append(evaluate_scenario(scenario, policy))
    failure_counts: dict[str, int] = {}
    for result in results:
        for code in result["codes"]:
            failure_counts[code] = failure_counts.get(code, 0) + 1
    named = sorted(result["id"] for result in results if not result["valid"])
    return {
        "valid": not errors and not named,
        "results": results,
        "named_blockers": named,
        "failure_counts": dict(sorted(failure_counts.items())),
        "errors": errors,
    }


def load_pack(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fixture pack must be an object")
    return value
