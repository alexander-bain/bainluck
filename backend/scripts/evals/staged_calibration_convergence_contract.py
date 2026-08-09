"""State-machine oracle for a resumable staged calibration population build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/staged_calibration_convergence_contract.json"


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def evaluate(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    prior = set(case.get("prior_units", []))
    planned = set(case.get("planned_units", []))
    changed = set(case.get("changed_units", []))
    kept = (prior & planned) - changed
    dropped = prior - kept
    completed = set(case.get("completed_this_beat", []))
    banked = kept | completed

    if case.get("prior_terminal") == "complete" and prior:
        errors.append("COMPLETED_CURSOR_REUSED")
    if case.get("prior_age_s", 0) > policy["max_in_progress_age_s"] and prior:
        errors.append("STALE_IN_PROGRESS_CURSOR")
    if changed & kept:
        errors.append("CHANGED_UNIT_RETAINED")
    if not case.get("same_population_version", True) and prior:
        errors.append("VERSION_MISMATCH_RETAINED")
    if not case.get("same_input_fingerprint", True) and prior:
        errors.append("INPUT_MISMATCH_RETAINED")

    concurrent = bool(case.get("concurrent_workers"))
    if concurrent and not case.get("claim_persisted_before_read"):
        errors.append("NON_ATOMIC_CLAIM")
    if case.get("cursor_write_status") == "superseded" and case.get("counted_as_durable"):
        errors.append("SUPERSEDED_COUNTED_DURABLE")
    if concurrent and case.get("whole_payload_replacement"):
        errors.append("LOST_UPDATE_POSSIBLE")

    if case.get("publish_attempted") and banked != planned:
        errors.append("PARTIAL_GENERATION_PUBLISHED")
    if case.get("publish_succeeded") and not case.get("cursor_cleared_after_publish"):
        errors.append("CURSOR_NOT_CLEARED_AFTER_PUBLISH")
    if case.get("gate_refused") and not case.get("cursor_cleared_after_refusal"):
        errors.append("REJECTED_INPUT_REUSABLE")

    progress = len(completed)
    if len(dropped) >= progress and dropped:
        warnings.append("NON_CONVERGING_BEAT")
    if case.get("cursor_ttl_lost") and prior:
        warnings.append("DURABLE_PROGRESS_LOST")

    return {
        "verdict": "refuse" if errors else ("watch" if warnings else "accept"),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "kept_units": sorted(kept),
        "banked_units": sorted(banked),
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    passed = 0
    for case in pack["cases"]:
        actual = evaluate(case["input"], pack["policy"])
        mismatches = [] if actual == case["expected"] else ["EXPECTED_RESULT_MISMATCH"]
        passed += not mismatches
        rows.append({"id": case["id"], "actual": actual, "expected_mismatches": mismatches})
    return {"cases": len(rows), "passed": passed, "results": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
