"""Pure C81 validators for lifecycle authority and one-card probability truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LIFECYCLE_FIXTURES = ROOT / "real_world_lifecycle_fixtures.json"
PROBABILITY_FIXTURES = ROOT / "card_probability_authority_fixtures.json"


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_lifecycle(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    current = row.get("evidence_freshness") == "current"
    conflict = bool(row.get("authority_conflict"))
    reopened = bool(row.get("correction_reopen"))
    completed = current and not conflict and not reopened and (
        row.get("linked_event_status") in {"completed", "closed"}
        or row.get("provider_settlement") == "confirmed"
        or row.get("winner_resolution_source") in corpus["authoritative_winner_sources"]
    )
    expected_suppress = completed or row.get("market_status") in {"resolved", "closed"}
    if row.get("suppress_live_prediction") != expected_suppress:
        errors.append("completion_decision_mismatch")

    if row.get("declared_state") == "live" and row.get("start_relation") == "future":
        errors.append("live_before_start")
    if reopened and row.get("declared_state") == "settled":
        errors.append("reopen_retains_settled_state")
    if conflict and row.get("suppress_live_prediction"):
        errors.append("conflict_hard_suppressed")
    if row.get("settled_from_price_only"):
        errors.append("price_used_as_authority")
    return errors


def _basis_map(row: dict[str, Any]) -> dict[str, float]:
    selected = row.get("display_basis")
    return {
        item["name"]: float(item["probability"])
        for item in row.get(f"{selected}_outcomes", [])
    }


def validate_probability(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("display_basis") not in {"raw", "normalized"}:
        return ["missing_display_basis"]
    authority = _basis_map(row)
    visible: dict[str, list[float]] = {}
    for surface in corpus["visible_probability_surfaces"]:
        for item in row.get(surface, []):
            name = item["name"]
            value = float(item["probability"])
            visible.setdefault(name, []).append(value)
            if name not in authority or round(value * 100) != round(authority[name] * 100):
                errors.append(f"{surface}_authority_mismatch:{name}")
    for name, values in visible.items():
        if len({round(value * 100) for value in values}) > 1:
            errors.append(f"visible_probability_divergence:{name}")

    widths: dict[int, set[int]] = {}
    for item in row.get("bar_rows", []):
        label = round(float(item["probability"]) * 100)
        widths.setdefault(label, set()).add(int(item["bar_width_pct"]))
    if any(len(group) > 1 for group in widths.values()):
        errors.append("equal_label_unequal_bar")
    return errors


def evaluate(corpus: dict[str, Any], validator: Any) -> dict[str, dict[str, list[str]]]:
    return {
        "accepted": {row["id"]: validator(row, corpus) for row in corpus["scenarios"]},
        "rejected": {
            row["id"]: validator(row, corpus)
            for row in corpus.get("rejected_counterexamples", [])
        },
    }


def main() -> int:
    lifecycle = load_fixture(LIFECYCLE_FIXTURES)
    probability = load_fixture(PROBABILITY_FIXTURES)
    print(json.dumps({
        "lifecycle": evaluate(lifecycle, validate_lifecycle),
        "probability": evaluate(probability, validate_probability),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
