"""Native-surface authority extension of canonical native_parity_inventory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/native_surface_authority_contract.json"


def evaluate(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if case.get("winner_emphasized") and (
        case.get("home_score") is None or case.get("away_score") is None
    ):
        errors.append("WINNER_WITH_INCOMPLETE_SCORE")
    if case.get("score_rendered") and (
        case.get("home_score") is None or case.get("away_score") is None
    ):
        errors.append("MISSING_SCORE_RENDERED_AS_ZERO")
    if case.get("analytics_emitted") and not case.get("consent_granted"):
        errors.append("ANALYTICS_WITHOUT_CONSENT")
    if case.get("push_transport") == "fcm" and case.get("registered_token_kind") != "fcm":
        errors.append("PUSH_TOKEN_KIND_MISMATCH")
    if case.get("notification_url") and not case.get("deep_link_handled"):
        errors.append("NOTIFICATION_DEEP_LINK_DROPPED")
    if case.get("settled") and case.get("live_probability_rendered"):
        errors.append("SETTLED_SURFACE_RENDERS_LIVE_PROBABILITY")
    return sorted(errors)


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in payload["cases"]:
        actual = evaluate(case["input"])
        expected = sorted(case["expected_refusals"])
        rows.append({"id": case["id"], "actual": actual, "ok": actual == expected})
    return {"total": len(rows), "passed": sum(row["ok"] for row in rows), "cases": rows}


def main() -> int:
    result = evaluate_corpus(json.loads(FIXTURE.read_text()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
