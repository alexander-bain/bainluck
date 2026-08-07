"""Dependency-free oracle for settled-score repair authority and apply safety."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURES = Path(__file__).resolve().parents[2] / "tests/evals/fixtures/settled_score_repair_contract.json"
ALLOWED_MUTATIONS = {"home_score", "away_score"}


def decide(case: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    authority = case["authority"]
    stored = case["stored"]

    if authority.get("disposition") not in {"final", "final_tie"}:
        reasons.append("disposition_not_final")
    if not authority.get("same_event_date"):
        reasons.append("event_date_mismatch")
    if not authority.get("same_orientation"):
        reasons.append("identity_or_orientation_mismatch")
    if authority.get("provider_disagreement"):
        reasons.append("provider_disagreement")
    if authority.get("timestamp_order_valid", True) is not True:
        reasons.append("authority_timestamp_invalid")
    if authority.get("home_score") is None or authority.get("away_score") is None:
        reasons.append("authority_score_missing")
    if case.get("event_timestamps_valid") is not True:
        reasons.append("event_timestamp_invalid")

    observed = case.get("apply_observed")
    if observed is not None and observed != stored:
        reasons.append("concurrent_change")
    if case.get("failure_stage"):
        reasons.append("atomic_apply_failed")

    requested = set(case.get("requested_mutations", []))
    if requested - ALLOWED_MUTATIONS:
        reasons.append("mutation_outside_allowlist")

    if reasons:
        return {"verdict": "refuse", "reasons": sorted(reasons), "mutations": []}

    final = {"home_score": authority["home_score"], "away_score": authority["away_score"]}
    if final == stored:
        return {"verdict": "noop", "reasons": ["already_authoritative"], "mutations": []}

    home_result = 1.0 if final["home_score"] > final["away_score"] else 0.0
    if final["home_score"] == final["away_score"]:
        home_result = 0.5
    mutations = ["home_score", "away_score"]
    return {
        "verdict": "repair",
        "reasons": ["authoritative_final_differs"],
        "mutations": mutations,
        "final_result": home_result,
    }


def evaluate(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in pack["cases"]:
        actual = decide(case)
        expected = case["expected"]
        rows.append({"id": case["id"], "passed": actual == expected, "actual": actual})
    return {"total": len(rows), "passed": sum(row["passed"] for row in rows), "cases": rows}


def load() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


if __name__ == "__main__":
    print(json.dumps(evaluate(load()), indent=2, sort_keys=True))
