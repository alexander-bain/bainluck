"""Dependency-free oracle for range-card probability and display truth."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


FIXTURES = Path(__file__).resolve().parents[2] / "tests/evals/fixtures/range_card_distribution_truth_contract.json"


def decide(case: dict[str, Any]) -> dict[str, Any]:
    rows = case.get("rows")
    if not isinstance(rows, list) or not rows:
        return {"verdict": "withhold", "reason": "no_distribution"}
    labels: set[str] = set()
    probs: list[float] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("label"), str):
            return {"verdict": "refuse", "reason": "invalid_row"}
        label = row["label"].strip().lower()
        value = row.get("probability")
        if not label or label in labels:
            return {"verdict": "refuse", "reason": "duplicate_or_empty_bucket"}
        labels.add(label)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            return {"verdict": "refuse", "reason": "invalid_probability"}
        probs.append(float(value))

    structure = case.get("structure", "unknown")
    if structure == "unknown":
        return {"verdict": "refuse", "reason": "structure_unknown"}
    if case.get("complete_set") is False and structure == "exclusive":
        return {"verdict": "refuse", "reason": "exclusive_set_incomplete"}
    if case.get("ranges_valid") is False:
        return {"verdict": "refuse", "reason": "range_partition_invalid"}
    if case.get("same_market_generation") is False:
        return {"verdict": "refuse", "reason": "cross_market_poison"}
    if len(probs) >= 4 and max(probs) - min(probs) < 1e-9 and abs(probs[0] - 0.5) < 1e-9 and not case.get("signal_evidence"):
        return {"verdict": "withhold", "reason": "degenerate_half_default"}
    if structure == "exclusive":
        total = sum(probs)
        tolerance = float(case.get("sum_tolerance", 0.02))
        if abs(total - 1.0) > tolerance:
            return {"verdict": "refuse", "reason": "exclusive_sum_invalid"}
    return {"verdict": "render", "reason": f"valid_{structure}"}


def display(case: dict[str, Any]) -> dict[str, Any]:
    probability = case.get("probability")
    printed = case.get("printed_probability")
    fill = case.get("fill_fraction")
    widths = case.get("track_widths", [])
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (probability, printed, fill)):
        return {"verdict": "refuse", "reason": "invalid_display_number"}
    if abs(float(probability) - float(printed)) > 0.005 or abs(float(probability) - float(fill)) > 0.005:
        return {"verdict": "refuse", "reason": "text_fill_basis_mismatch"}
    if widths and max(widths) - min(widths) > 0.5:
        return {"verdict": "refuse", "reason": "unstable_track_width"}
    return {"verdict": "render", "reason": "pixel_contract_honest"}


def load() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


def evaluate(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in pack["cases"]:
        actual = display(case) if case["kind"] == "display" else decide(case)
        rows.append({"id": case["id"], "passed": actual == case["expected"], "actual": actual})
    return {"total": len(rows), "passed": sum(row["passed"] for row in rows), "cases": rows}


if __name__ == "__main__":
    print(json.dumps(evaluate(load()), indent=2, sort_keys=True))
