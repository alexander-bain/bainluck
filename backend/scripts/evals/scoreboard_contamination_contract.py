"""Dependency-free C141 oracle for feed-card ownership and display truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "scoreboard-contamination-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "scoreboard_contamination_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)):
        raise ValueError("CASE_IDS_INVALID")
    defaults = payload.get("defaults") or {}
    payload["cases"] = [{**defaults, **row} for row in cases]
    return payload


def refusal_codes(row: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    market = row.get("market") or {}
    members = row.get("members") or []
    outcomes = row.get("outcomes") or []

    for member in members:
        if member.get("group_id") != market.get("group_id"):
            codes.append("GROUP_ID_MISMATCH")
        if member.get("event_id") != market.get("event_id"):
            codes.append("CROSS_EVENT_MEMBER")
        if member.get("domain") != market.get("domain"):
            codes.append("CROSS_DOMAIN_MEMBER")
        if member.get("competition") != market.get("competition"):
            codes.append("CROSS_COMPETITION_MEMBER")
        if member.get("gender") != market.get("gender"):
            codes.append("CROSS_GENDER_MEMBER")

    outcome_ids = [o.get("id") for o in outcomes]
    if len(outcome_ids) != len(set(outcome_ids)):
        codes.append("DUPLICATE_OUTCOME_ID")
    if any(o.get("market_id") != market.get("id") for o in outcomes):
        codes.append("CROSS_MARKET_OUTCOME")

    if market.get("expected_winners") == 1:
        winner_count = sum(bool(o.get("winner")) for o in outcomes)
        if winner_count > 1:
            codes.append("DUPLICATE_SINGLE_WINNER")

    visible = [o for o in outcomes if o.get("visible", True)]
    priced_visible = [o for o in visible if isinstance(o.get("probability"), (int, float))]
    if priced_visible:
        actual_leader = max(priced_visible, key=lambda o: o["probability"]).get("id")
        if row.get("visible_leader_id") != actual_leader:
            codes.append("VISIBLE_LEADER_WRONG")
    if row.get("raw_leader_id") and row.get("raw_leader_id") not in outcome_ids:
        codes.append("AUTHORITATIVE_LEADER_MISSING")

    if market.get("mutually_exclusive") and market.get("complete"):
        total = sum(float(o.get("probability") or 0) for o in outcomes)
        if not 0.98 <= total <= 1.02:
            codes.append("COMPLETE_EXCLUSIVE_SUM_INVALID")
    if market.get("mutually_exclusive") and not market.get("complete") and row.get("normalized"):
        codes.append("INCOMPLETE_SET_NORMALIZED")

    ladder = row.get("ladder") or {}
    if ladder:
        rungs = ladder.get("rungs") or []
        if any(r.get("parsed") is not True or not isinstance(r.get("value"), (int, float)) for r in rungs):
            codes.append("UNPARSED_THRESHOLD")
        values = [r.get("value") for r in rungs if isinstance(r.get("value"), (int, float))]
        if len(values) != len(set(values)):
            codes.append("DUPLICATE_THRESHOLD_VALUE")
        labels = [r.get("label") for r in rungs]
        if len(labels) != len(set(labels)):
            codes.append("COLLAPSED_THRESHOLD_LABEL")
        if any(r.get("operator") not in {"at_least", "at_most", "exact", "range"} for r in rungs):
            codes.append("THRESHOLD_OPERATOR_INVALID")
        if values != sorted(values):
            codes.append("LADDER_ORDER_WRONG")
        probs = [r.get("probability") for r in rungs]
        if all(isinstance(p, (int, float)) for p in probs):
            operators = {r.get("operator") for r in rungs}
            if operators == {"at_least"} and probs != sorted(probs, reverse=True):
                codes.append("LADDER_MONOTONICITY_BROKEN")
            if operators == {"at_most"} and probs != sorted(probs):
                codes.append("LADDER_MONOTONICITY_BROKEN")

    if row.get("poison") and not row.get("clean_sibling_preserved"):
        codes.append("POISON_ERASED_CLEAN_SIBLING")

    closure = row.get("closure") or {}
    if closure.get("claimed_shipped_good"):
        rendered = bool(
            closure.get("deployed_sha")
            and closure.get("pinned_identity_checked")
            and closure.get("rendered_terminal") in {"gone", "honestly_settled", "corrected"}
            and closure.get("adjacent_clean")
            and closure.get("replacement_scan_clean")
        )
        if not rendered:
            codes.append("RENDERED_CLOSURE_EVIDENCE_MISSING")
    return sorted(set(codes))


def classify(row: dict[str, Any]) -> str:
    return "SHIPPED_GOOD" if not refusal_codes(row) and (row.get("closure") or {}).get("claimed_shipped_good") else "NOT_OBSERVABLE"


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    results = []
    for row in corpus["cases"]:
        actual = refusal_codes(row)
        expected = sorted(row.get("expected_refusals") or [])
        status = classify(row)
        results.append({"id": row["id"], "ok": actual == expected and status == row.get("expected_status"), "actual": actual, "status": status})
    return {"total": len(results), "passed": sum(r["ok"] for r in results), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
