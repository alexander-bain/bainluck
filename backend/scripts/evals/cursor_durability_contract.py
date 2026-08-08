"""Dependency-free oracle for durable cursor and replay semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/cursor_durability_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "cursor-durability-contract/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    c = row["cursor"]
    selected = list(c.get("selected", []))
    attempted = list(c.get("attempted", []))
    committed = list(c.get("committed", []))
    next_cursor = c.get("next")
    idempotent = c.get("idempotent") is True
    reasons: list[str] = []

    unattempted = [item for item in selected if item not in attempted]
    uncommitted = [item for item in attempted if item not in committed]
    lost = [item for item in selected if next_cursor is not None and item <= next_cursor and item not in committed]
    replay = [item for item in committed if next_cursor is None or item > next_cursor]

    if lost:
        reasons.append("CURSOR_ADVANCES_PAST_DURABLE_WORK")
    if unattempted and c.get("terminal") == "complete":
        reasons.append("COMPLETE_WITH_UNATTEMPTED_WORK")
    if uncommitted and c.get("terminal") == "complete":
        reasons.append("COMPLETE_WITH_UNCOMMITTED_WORK")
    if replay and not idempotent:
        reasons.append("NON_IDEMPOTENT_REPLAY")
    if c.get("cursor_written_before_work"):
        reasons.append("CURSOR_WRITTEN_BEFORE_WORK")
    if c.get("lease_required") and not c.get("lease_held"):
        reasons.append("CONCURRENT_CURSOR_UNLEASED")
    if c.get("empty_page") and c.get("upstream_next") and c.get("terminal") == "complete":
        reasons.append("EMPTY_PAGE_PREMATURE_TERMINATION")
    if c.get("ttl_expired") and not idempotent:
        reasons.append("TTL_LOSS_REPLAYS_UNSAFE")

    if lost:
        classification = "SKIPS_WORK"
    elif replay:
        classification = "REPLAYS_SAFE" if idempotent else "REPLAYS_UNSAFE"
    else:
        classification = "SAFE"
    verdict = "REFUSE" if reasons else "PASS"
    return {
        "verdict": verdict,
        "classification": classification,
        "lost_ids": lost,
        "replay_ids": replay,
        "reason_codes": sorted(set(reasons)),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda item: item["id"]):
        actual = evaluate_case(row)
        details.append({"id": row["id"], "actual": actual, "expected": row["expected"], "passed": actual == row["expected"]})
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
