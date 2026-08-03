"""Dependency-free contract for the soccer-first game-market classifier cycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "soccer-classifier-contract/v1"
FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "soccer_classifier_contract.json"
)

COARSE_BY_KIND = {
    "whole_game_winner": "moneyline",
    "period_winner": "team_prop",
    "spread": "spread",
    "total": "total",
    "player_prop": "player_prop",
    "team_prop": "team_prop",
    "other": "other",
}
ALLOWED_SPORT_PREFIXES = ("soccer_", "esports", "baseball_")


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
    kind = row.get("semantic_kind")
    expected = row.get("expected_class")
    if kind not in COARSE_BY_KIND:
        errors.append("SEMANTIC_KIND_INVALID")
    elif expected != COARSE_BY_KIND[kind]:
        errors.append("EXPECTED_CLASS_DRIFT")

    sport = row.get("sport") or ""
    if not sport.startswith(ALLOWED_SPORT_PREFIXES):
        errors.append("SPORT_SCOPE_INVALID")
    if not isinstance(row.get("name"), str) or not row["name"].strip():
        errors.append("NAME_REQUIRED")

    outcomes = row.get("outcome_shape")
    if outcomes == "player_contracts" and expected != "player_prop":
        errors.append("PLAYER_CONTAINER_BECAME_WINNER")
    if outcomes == "three_way_home_draw_away":
        if kind not in {"whole_game_winner", "period_winner"} or not row.get("draw_preserved"):
            errors.append("SOCCER_DRAW_CONTRACT_LOST")
    if kind == "period_winner" and not row.get("period"):
        errors.append("PERIOD_IDENTITY_REQUIRED")
    if kind == "whole_game_winner" and row.get("period"):
        errors.append("PERIOD_WINNER_BECAME_MONEYLINE")
    if row.get("cross_event_identity"):
        errors.append("CROSS_EVENT_IDENTITY_ALLOWED")
    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for row in corpus["cases"]:
        actual = evaluate_case(row)
        expected = sorted(row.get("expected_refusals") or [])
        cases.append({"id": row["id"], "ok": actual == expected, "actual": actual})
    return {
        "total": len(cases),
        "passed": sum(case["ok"] for case in cases),
        "cases": cases,
    }


def audit_classifier(
    corpus: dict[str, Any], classifier: Callable[[str, str | None, str | None], str]
) -> list[dict[str, str]]:
    """Return stable production mismatches; outcome-aware consumers may rescue rows."""
    mismatches = []
    for row in corpus["cases"]:
        actual = classifier(row["name"], row.get("external_id"), row.get("sport"))
        if actual != row["expected_class"]:
            mismatches.append({"id": row["id"], "expected": row["expected_class"], "actual": actual})
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
