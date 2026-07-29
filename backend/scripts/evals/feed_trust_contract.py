"""Pure C79 contracts for Discover credibility and request/render speed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CREDIBILITY_FIXTURES = ROOT / "feed_credibility_fixtures.json"
SPEED_FIXTURES = ROOT / "feed_speed_fixtures.json"


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_credibility(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    authoritative_stale = (
        row.get("market_status") in {"closed", "resolved"}
        or row.get("resolution_date_relation") == "past"
        or row.get("linked_event_status") in {"completed", "closed"}
    )
    has_rendered_probability = any(
        outcome.get("probability") is not None
        for outcome in row.get("rendered_outcomes", [])
    )
    expected_surface = not authoritative_stale and has_rendered_probability
    if row.get("surface") != expected_surface:
        errors.append("surfacing_decision_mismatch")

    if not authoritative_stale and row.get("surface") is False and row.get("leader_probability", 0) >= 0.95:
        errors.append("price_only_settlement")

    authority = row.get("display_probability_authority")
    if authority is not None:
        rounded = round(float(authority) * 100)
        for field in ("headline_pct", "subtitle_pct", "list_pct"):
            value = row.get(field)
            if value is not None and value != rounded:
                errors.append(f"{field}_authority_mismatch")

    equal_groups: dict[int, set[int]] = {}
    for outcome in row.get("display_outcomes", []):
        pct = round(float(outcome["probability"]) * 100)
        equal_groups.setdefault(pct, set()).add(int(outcome["bar_width_pct"]))
    if any(len(widths) > 1 for widths in equal_groups.values()):
        errors.append("equal_label_unequal_bar")
    return errors


def validate_speed(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    requests = row.get("requests", [])
    initial = [request for request in requests if request.get("phase") == "initial"]
    if len(initial) != 1:
        errors.append("initial_request_count")
    if initial and initial[0].get("limit", 0) > corpus["initial_page_limit_max"]:
        errors.append("initial_page_unbounded")

    for request in requests:
        if request.get("phase") == "revalidation" and request.get("trigger") not in corpus["real_revalidation_triggers"]:
            errors.append("spurious_revalidation")

    pagination = [request for request in requests if request.get("phase") == "pagination"]
    offsets = [int(request["offset"]) for request in pagination]
    if offsets != sorted(set(offsets)) or any(offset <= 0 for offset in offsets):
        errors.append("non_monotonic_pagination")
    if initial and any(request.get("offset") == initial[0].get("offset") for request in pagination):
        errors.append("initial_page_refetched_as_pagination")

    rendered = row.get("rendered_ids", [])
    if len(rendered) != len(set(rendered)):
        errors.append("duplicate_render_id")
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
    credibility = load_fixture(CREDIBILITY_FIXTURES)
    speed = load_fixture(SPEED_FIXTURES)
    print(json.dumps({
        "credibility": evaluate(credibility, validate_credibility),
        "speed": evaluate(speed, validate_speed),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
