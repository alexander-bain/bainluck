"""Pure C89 contract for lifecycle writes at the event-registry boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).with_name("precommence_live_authority_fixtures.json")
START_AUTHORITIES = {"odds_api", "statpal", "official_schedule"}
TERMINAL = {"completed", "closed"}


def load_corpus() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


def authoritative_start_passed(row: dict[str, Any]) -> bool:
    return (
        row.get("commence_confidence") in START_AUTHORITIES
        and row.get("start_relation") == "past"
    )


def resolve_write(row: dict[str, Any]) -> dict[str, Any]:
    prior = row.get("prior_status") or "scheduled"
    incoming = row.get("incoming_status")
    transition = row.get("schedule_transition")
    started = authoritative_start_passed(row)

    if transition in {"postponed", "rescheduled", "doubleheader_sibling"}:
        stored = "scheduled"
    elif incoming in TERMINAL:
        stored = incoming
    elif incoming == "live":
        if prior in TERMINAL:
            stored = "live" if transition == "replay" and started else prior
        else:
            stored = "live" if started else "scheduled"
    elif incoming == "scheduled":
        stored = "scheduled"
    else:
        stored = prior

    display = "live" if stored == "live" else "settled" if stored in TERMINAL else "upcoming"
    repair = bool(
        row.get("existing_row")
        and prior == "live"
        and row.get("start_relation") == "future"
        and row.get("commence_confidence") in START_AUTHORITIES
    )
    sentinel = "red_before_repair" if repair else "green"
    return {
        "stored_status": stored,
        "display_status": display,
        "sentinel": sentinel,
        "repair_eligible": repair,
        "suppress_card": False,
    }


def validate_scenario(row: dict[str, Any]) -> list[str]:
    actual = resolve_write(row)
    errors = []
    for field in ("stored_status", "display_status", "sentinel", "repair_eligible"):
        if actual[field] != row.get(f"expected_{field}"):
            errors.append(f"{field}_mismatch")
    return errors


def validate_claim(row: dict[str, Any]) -> list[str]:
    errors = []
    claimed = row.get("claimed_stored_status")
    if claimed == "live" and not authoritative_start_passed(row):
        errors.append("live_without_authoritative_start")
    if row.get("prior_status") in TERMINAL and claimed == "live" and not (
        row.get("schedule_transition") == "replay" and authoritative_start_passed(row)
    ):
        errors.append("terminal_reopened_without_started_authority")
    if (
        row.get("start_relation") == "unknown"
        and row.get("claimed_suppress_card")
    ):
        errors.append("unknown_start_suppressed_card")
    return errors


def evaluate(corpus: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted": {row["id"]: validate_scenario(row) for row in corpus["scenarios"]},
        "rejected": {row["id"]: validate_claim(row) for row in corpus["rejected_counterexamples"]},
    }


def main() -> int:
    print(json.dumps(evaluate(load_corpus()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
