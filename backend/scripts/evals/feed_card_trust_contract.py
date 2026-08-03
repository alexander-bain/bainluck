"""Dependency-free C137 contract for settled and outcome-list feed-card truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "feed-card-trust-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "feed_card_trust_contract.json"


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
    return payload


def evaluate_case(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lifecycle = row.get("lifecycle") or {}
    action = row.get("actual_action")
    authoritative_end = bool(
        lifecycle.get("authoritative_terminal")
        or lifecycle.get("resolution_date_past")
        or (lifecycle.get("title_date_past") and lifecycle.get("linked_event_past"))
    )
    expected_action = "settle_or_hide" if authoritative_end else "include"
    if action != expected_action:
        errors.append("LIFECYCLE_ACTION_WRONG")
    if lifecycle.get("title_date_past") and not lifecycle.get("linked_event_past") and action != "include":
        errors.append("TITLE_ONLY_SUPPRESSION")
    if lifecycle.get("price_extreme") and not authoritative_end and action != "include":
        errors.append("PRICE_ONLY_SUPPRESSION")

    outcomes = row.get("outcomes") or []
    market_id = row.get("market_id")
    ids = [o.get("id") for o in outcomes]
    if len(ids) != len(set(ids)):
        errors.append("DUPLICATE_OUTCOME_ID")
    if any(o.get("market_id") != market_id for o in outcomes):
        errors.append("CROSS_MARKET_OUTCOME")
    priced = [o for o in outcomes if isinstance(o.get("probability"), (int, float))]
    if priced and row.get("expected_leader_id"):
        actual_leader = max(priced, key=lambda o: o["probability"]).get("id")
        if actual_leader != row["expected_leader_id"]:
            errors.append("ACTUAL_LEADER_MISSING")
    if row.get("mutually_exclusive") and row.get("complete"):
        total = sum(o.get("probability") or 0 for o in outcomes)
        if not 0.98 <= total <= 1.02:
            errors.append("COMPLETE_EXCLUSIVE_SUM_INVALID")
    if row.get("mutually_exclusive") and not row.get("complete") and row.get("normalized"):
        errors.append("INCOMPLETE_SET_NORMALIZED")

    ladder = row.get("ladder") or {}
    if ladder:
        rungs = ladder.get("rungs") or []
        thresholds = [r.get("threshold") for r in rungs]
        probs = [r.get("probability") for r in rungs]
        if thresholds != sorted(thresholds):
            errors.append("LADDER_THRESHOLD_ORDER_WRONG")
        direction = ladder.get("direction")
        if direction == "at_least" and probs != sorted(probs, reverse=True):
            errors.append("LADDER_MONOTONICITY_BROKEN")
        if direction == "at_most" and probs != sorted(probs):
            errors.append("LADDER_MONOTONICITY_BROKEN")

    response = row.get("response") or {}
    if response.get("quality") in {"partial", "unavailable", "failed"} and response.get("replaced_last_good"):
        errors.append("BAD_BUILD_REPLACED_LAST_GOOD")
    if response.get("poison_sibling") and not response.get("clean_sibling_preserved"):
        errors.append("POISON_SIBLING_ERASED_CLEAN_CARD")
    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for row in corpus["cases"]:
        actual = evaluate_case(row)
        expected = sorted(row.get("expected_refusals") or [])
        cases.append({"id": row["id"], "ok": actual == expected, "actual": actual})
    return {"total": len(cases), "passed": sum(c["ok"] for c in cases), "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
