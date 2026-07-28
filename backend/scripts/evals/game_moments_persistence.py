#!/usr/bin/env python3
"""Offline persistence invariants for the game-moments repair (C59)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
TERMINAL_STATES = {"written", "empty", "failed", "cancelled"}


def load_pack(path: Path) -> dict[str, Any]:
    pack = json.loads(path.read_text())
    if pack.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if not isinstance(pack.get("cases"), list):
        raise ValueError("cases must be a list")
    return pack


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    computed = case["computed_moments"]
    keys = [moment["derived_key"] for moment in computed]
    canonical = case["observations"].get("canonical_keys", keys)
    existing = case["existing_keys"]
    final = case["observations"]["final_keys"]
    terminal = case["observations"]["terminal_state"]

    if len(keys) != len(set(keys)):
        findings.append("DERIVED_IDENTITY_COLLISION")
    if len(canonical) != len(set(canonical)):
        findings.append("CANONICAL_IDENTITY_NOT_UNIQUE")
    if terminal not in TERMINAL_STATES:
        findings.append("MISSING_TERMINAL_STATE")

    fetch = case["fetch_state"]
    if fetch == "failed":
        if final != existing:
            findings.append("FETCH_FAILURE_REPLACED_EVIDENCE")
    elif fetch == "computed":
        expected_final = sorted(canonical)
        if sorted(final) != expected_final:
            findings.append("AUTHORITATIVE_FINAL_STATE_MISMATCH")

    obs = case["observations"]
    if obs.get("partial_state_visible"):
        findings.append("PARTIAL_REPLACEMENT_VISIBLE")
    if obs.get("overlap") and not (obs.get("serialized") or obs.get("conflict_safe")):
        findings.append("OVERLAP_UNSAFE")
    if terminal == "failed" and case.get("later_sibling_selected"):
        if not obs.get("later_sibling_terminal"):
            findings.append("FAILED_EVENT_ABORTED_SIBLING")
    if obs.get("rollback_expired_orm_read"):
        findings.append("ROLLBACK_EXPIRED_ORM_ACCESS")

    expected = sorted(case["expected_findings"])
    if sorted(findings) != expected:
        findings.append("EXPECTED_FINDINGS_MISMATCH")
    return {"id": case["id"], "terminal_state": terminal, "findings": findings}


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    results = [evaluate_case(case) for case in pack["cases"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "cases": len(results),
        "unsafe_cases": sum(bool(row["findings"]) for row in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(__file__).with_name("game_moments_persistence_fixtures.json"),
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_pack(load_pack(args.fixtures)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
