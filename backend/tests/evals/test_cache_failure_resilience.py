from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.evals.cache_failure_resilience import (
    evaluate_pack,
    evaluate_scenario,
    load_pack,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "cache_failure_resilience_fixtures.json"
)


@pytest.fixture(scope="module")
def pack() -> dict:
    return load_pack(FIXTURE)


def _result(report: dict, scenario_id: str) -> dict:
    return next(row for row in report["results"] if row["id"] == scenario_id)


def test_fixture_has_every_required_scenario(pack: dict) -> None:
    ids = {row["id"] for row in pack["scenarios"]}
    assert {
        "redis-connect-error",
        "redis-read-never-returns",
        "runtime-config-precache-stall",
        "fresh-miss-stale-hit-clean",
        "redis-unavailable-local-last-good",
        "calibration-sync-block",
        "twenty-request-stampede",
        "thin-feed-second-pass",
        "db-checkout-wait",
        "compute-deadline",
        "cache-write-stall",
        "malformed-cache-json",
        "metrics-sink-unavailable",
    } == ids


def test_clean_stale_hit_is_valid(pack: dict) -> None:
    result = evaluate_scenario(
        next(
            row
            for row in pack["scenarios"]
            if row["id"] == "fresh-miss-stale-hit-clean"
        ),
        pack["policy"],
    )
    assert result == {
        "id": "fresh-miss-stale-hit-clean",
        "valid": True,
        "codes": [],
        "findings": [],
    }


@pytest.mark.parametrize(
    ("scenario_id", "code"),
    [
        ("redis-connect-error", "CLIENT_NOT_CLOSED"),
        ("redis-read-never-returns", "REDIS_OPERATION_OVER_DEADLINE"),
        ("runtime-config-precache-stall", "ROUTER_BUDGET_EXCEEDED"),
        ("redis-unavailable-local-last-good", "COLD_COMPUTE_WITH_LAST_GOOD"),
        ("calibration-sync-block", "EVENT_LOOP_BLOCKED"),
        ("twenty-request-stampede", "BUILD_STAMPEDE"),
        ("thin-feed-second-pass", "REPEATED_COMPUTE_OVER_BUDGET"),
        ("db-checkout-wait", "DB_CHECKOUT_OVER_DEADLINE"),
        ("compute-deadline", "COMPUTE_DEADLINE_EXCEEDED"),
        ("cache-write-stall", "CACHE_WRITE_BLOCKED_RESPONSE"),
        ("malformed-cache-json", "MALFORMED_CACHE_UNTYPED"),
        ("metrics-sink-unavailable", "OBSERVABILITY_FALSE_GREEN"),
    ],
)
def test_named_fault_is_detected(pack: dict, scenario_id: str, code: str) -> None:
    assert code in _result(evaluate_pack(pack), scenario_id)["codes"]


def test_pack_never_masks_named_blockers(pack: dict) -> None:
    report = evaluate_pack(pack)
    assert report["valid"] is False
    assert report["named_blockers"] == sorted(
        row["id"]
        for row in pack["scenarios"]
        if row["id"] != "fresh-miss-stale-hit-clean"
    )
    assert sum(report["failure_counts"].values()) >= len(report["named_blockers"])


def test_policy_is_input_not_hidden_constant(pack: dict) -> None:
    scenario = next(
        row for row in pack["scenarios"] if row["id"] == "thin-feed-second-pass"
    )
    strict = evaluate_scenario(scenario, pack["policy"])
    relaxed_policy = {**pack["policy"], "compute_deadline_ms": 10000}
    relaxed = evaluate_scenario(scenario, relaxed_policy)
    assert "REPEATED_COMPUTE_OVER_BUDGET" in strict["codes"]
    assert "REPEATED_COMPUTE_OVER_BUDGET" not in relaxed["codes"]


def test_deterministic_output(pack: dict) -> None:
    assert evaluate_pack(pack) == evaluate_pack(copy.deepcopy(pack))


def test_invalid_policy_fails_closed(pack: dict) -> None:
    value = copy.deepcopy(pack)
    value["policy"].pop("router_timeout_ms")
    result = evaluate_pack(value)
    assert result["valid"] is False
    assert result["errors"][0]["code"] == "POLICY_INVALID"


def test_fixture_is_synthetic_and_contains_no_identity_data(pack: dict) -> None:
    text = FIXTURE.read_text(encoding="utf-8").lower()
    assert "email" not in text
    assert "token" not in text
    assert "user_id" not in text
