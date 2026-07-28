#!/usr/bin/env python3
"""Offline truth-state contract for Grid Sentinel freshness evidence (C58)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIRED_COCKPIT_FIELDS = {
    "evidence_state",
    "reason",
    "population_count",
    "newest_at",
}


def load_pack(path: Path) -> dict[str, Any]:
    pack = json.loads(path.read_text())
    if pack.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if not isinstance(pack.get("policy"), dict) or not isinstance(
        pack.get("cases"), list
    ):
        raise ValueError("pack requires policy and cases")
    return pack


def evaluate_case(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    query = case["query"]
    expected_ids = set(case["expected_market_ids"])
    observed_ids = {row["market_id"] for row in case["observed_rows"]}
    cockpit = case["cockpit"]

    if case["grid_http_state"] != "ok":
        state, verdict, filing = "unknown", "red", "file"
    elif query.get("error") or query.get("timed_out") or query.get("cancelled"):
        state, verdict, filing = "unknown", "unknown", "hold"
    elif observed_ids != expected_ids:
        state, verdict, filing = "unknown", "unknown", "hold"
        findings.append("POPULATION_MISMATCH")
    elif not observed_ids and case["phase"] == "active":
        state, verdict, filing = "stale", "red", "file"
    elif case["query_result"] == "stale" and case["phase"] == "active":
        state, verdict, filing = "stale", "red", "file"
    else:
        state, verdict, filing = "verified", "green", "close"

    if state == "unknown" and filing == "close":
        findings.append("UNKNOWN_CLOSED_ALERT")
    if case["prior_alert_state"] == "red" and state == "unknown" and filing != "hold":
        findings.append("UNKNOWN_DID_NOT_HOLD_PRIOR_RED")
    missing = sorted(REQUIRED_COCKPIT_FIELDS - set(cockpit))
    if missing:
        findings.append("COCKPIT_EVIDENCE_DROPPED:" + ",".join(missing))
    elif cockpit["evidence_state"] != state:
        findings.append("COCKPIT_STATE_MISMATCH")

    max_rows = int(policy["max_scanned_rows"])
    max_ms = int(policy["max_query_ms"])
    if query["scanned_rows"] > max_rows:
        findings.append("QUERY_SCAN_OVER_POLICY")
    if query["duration_ms"] > max_ms:
        findings.append("QUERY_DURATION_OVER_POLICY")
    if query.get("plan_facts") is None:
        findings.append("PLAN_UNMEASURED")

    expected = case["expected"]
    actual = {"evidence_state": state, "verdict": verdict, "filing": filing}
    if actual != expected:
        findings.append("EXPECTED_OUTCOME_MISMATCH")
    return {"id": case["id"], **actual, "findings": findings}


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    rows = [evaluate_case(case, pack["policy"]) for case in pack["cases"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "cases": len(rows),
        "unsafe_cases": sum(bool(row["findings"]) for row in rows),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(__file__).with_name("grid_freshness_truth_fixtures.json"),
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_pack(load_pack(args.fixtures)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
