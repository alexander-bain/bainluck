"""Dependency-free oracle for the program-lane integration boundary."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/program_integration_contract.json"


def load_corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def integration_decision(case: dict) -> dict:
    failures = list(case.get("failures", []))
    allowed = not failures
    return {
        "verdict": "ALLOW" if allowed else "REFUSE",
        "reason_codes": failures,
        "mutate_master": allowed,
        "recovery_owner": case.get("recovery_owner", "none" if allowed else "integrator"),
        "recovery": case.get("recovery", "proceed" if allowed else "collect valid evidence and retry"),
    }


def pilot_decision(record: dict) -> dict:
    cycles = record.get("cycles", [])
    valid_cycles = [cycle for cycle in cycles if cycle.get("complete") and not cycle.get("ambiguous")]
    if record.get("stop_required"):
        verdict = "STOP"
    elif len(valid_cycles) < 3 or not record.get("explicit_pilot_verdict"):
        verdict = "EXTEND_PILOT"
    elif any(cycle.get("rollback") or cycle.get("visible_payoff") is not True for cycle in valid_cycles[:3]):
        verdict = "AMEND_AND_EXTEND"
    else:
        verdict = "MIGRATE_MORE_PROGRAMS"
    return {"verdict": verdict, "valid_cycles": len(valid_cycles)}


def evaluate_corpus(corpus: dict) -> dict:
    results = []
    for case in corpus["integration_cases"]:
        actual = integration_decision(case)
        passed = (
            actual["verdict"] == case["expected_verdict"]
            and actual["reason_codes"] == case["expected_reason_codes"]
            and actual["mutate_master"] == case["expected_mutate_master"]
            and actual["recovery_owner"] == case["expected_recovery_owner"]
        )
        results.append({"id": case["id"], "passed": passed, "actual": actual})
    for record in corpus["pilot_cases"]:
        actual = pilot_decision(record)
        passed = actual["verdict"] == record["expected_verdict"]
        results.append({"id": record["id"], "passed": passed, "actual": actual})
    return {"total": len(results), "passed": sum(row["passed"] for row in results), "cases": results}


if __name__ == "__main__":
    print(json.dumps(evaluate_corpus(load_corpus()), indent=2, sort_keys=True))
