"""Canonical ordering contract for Discover's marquee and tonight-game leads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/discover_lead_order_contract.json"


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    before = case["before"]
    after = case["after"]
    errors: list[str] = []
    if sorted(before) != sorted(after) or len(before) != len(after):
        errors.append("MEMBERSHIP_CHANGED")
    if case.get("scores_before") != case.get("scores_after"):
        errors.append("SCORES_CHANGED")
    marquee = [item for item in after if item.startswith("marquee:")]
    games = [item for item in after if item.startswith("game:")]
    if marquee and games and after.index(marquee[0]) > after.index(games[0]):
        errors.append("MARQUEE_TOP_SLOT_DISPLACED")
    if not marquee and games and after[0] != games[0]:
        errors.append("TONIGHTS_GAME_DID_NOT_LEAD")
    return {"verdict": "REFUSE" if errors else "ALLOW", "errors": sorted(errors)}


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    rows = [{"id": row["id"], "actual": evaluate(row), "expected": row["expected"]} for row in pack["cases"]]
    return {"total": len(rows), "passed": sum(row["actual"] == row["expected"] for row in rows), "rows": rows}


def load_pack() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())
