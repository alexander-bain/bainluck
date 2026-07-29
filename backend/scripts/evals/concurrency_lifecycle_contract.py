"""Pure validators for C74's singleflight and native lifecycle fixture packs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FEED_FIXTURES = ROOT / "singleflight_deadline_fixtures.json"
NATIVE_FIXTURES = ROOT / "native_sports_lifecycle_fixtures.json"


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_feed_scenario(row: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    budget = int(policy["request_budget_ms"])
    router_cutoff = int(policy["router_cutoff_ms"])
    waits = [int(value) for value in row.get("waits_ms", [])]
    compute = int(row.get("compute_ms", 0))
    elapsed = sum(waits) + compute
    admitted = row.get("compute_admitted_at_ms")

    if elapsed > budget:
        errors.append("request_budget_exceeded")
    if elapsed > router_cutoff:
        errors.append("router_cutoff_exceeded")
    if admitted is not None and int(admitted) >= budget:
        errors.append("compute_admitted_after_deadline")
    if any(int(count) > 1 for count in row.get("owner_counts", [])):
        errors.append("multiple_executing_owners")
    if row.get("displaced_owner") == "orphaned":
        errors.append("displaced_owner_orphaned")
    if row.get("displaced_owner") not in {
        "none",
        "remains_owner",
        "cancelled_and_joined",
    }:
        if "displaced_owner_orphaned" not in errors:
            errors.append("invalid_displaced_owner_state")
    if row.get("terminal") not in set(policy["terminal_states"]):
        errors.append("invalid_terminal_state")
    return errors


def validate_native_scenario(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not row.get("task_terminated", False):
        errors.append("work_not_terminated")
    if row.get("termination_policy") == "discard_result_only":
        errors.append("discard_is_not_cancellation")
    if int(row.get("max_active_owned_loads", 0)) > 1:
        errors.append("multiple_active_owned_loads")

    token = row.get("render_token")
    publication = row.get("permitted_publication_generation")
    if token is not None:
        required = {"generation", "started_at", "provenance", "item_count"}
        if set(token) != required:
            errors.append("invalid_render_token")
        elif token["generation"] != publication:
            errors.append("render_generation_mismatch")
    if row.get("reads_live_mutable_count", False):
        errors.append("mutable_render_count")
    if row.get("requires_onappear_refire", False):
        errors.append("onappear_refire_assumption")
    return errors


def evaluate_corpus(corpus: dict[str, Any], validator: Any, *args: Any) -> dict[str, Any]:
    accepted = {row["id"]: validator(row, *args) for row in corpus["scenarios"]}
    rejected = {
        row["id"]: validator(row, *args)
        for row in corpus.get("rejected_counterexamples", [])
    }
    return {"accepted": accepted, "rejected": rejected}


def main() -> int:
    feed = load_fixture(FEED_FIXTURES)
    native = load_fixture(NATIVE_FIXTURES)
    result = {
        "feed": evaluate_corpus(feed, validate_feed_scenario, feed["policy"]),
        "native": evaluate_corpus(native, validate_native_scenario),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
