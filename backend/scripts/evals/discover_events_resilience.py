"""Offline resilience oracle for the discover_events checkpoint contract."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


FIXTURE_PATH = Path(__file__).with_name("discover_events_resilience_fixtures.json")
FAILURE_KINDS = {
    "none",
    "slow_odds",
    "hung_espn",
    "db_timeout_before_commit",
    "db_timeout_after_commit",
    "poison_event",
    "hard_kill_mid_unit",
    "hard_kill_between_units",
    "redis_marker_failure",
    "piggyback_failure",
}


@dataclass
class State:
    events: set[str] = field(default_factory=set)
    snapshots: set[str] = field(default_factory=set)
    markers: set[str] = field(default_factory=set)
    retry_cursor: list[str] = field(default_factory=list)
    marker_repairs: list[str] = field(default_factory=list)
    failed_units: list[str] = field(default_factory=list)
    piggyback_failures: int = 0
    duplicate_writes: int = 0
    cleanup_observed: bool = False


def load_fixtures(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported fixture schema")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("fixtures must be a non-empty list")
    names = [fixture.get("name") for fixture in fixtures]
    if len(names) != len(set(names)):
        raise ValueError("fixture names must be unique")
    for fixture in fixtures:
        validate_fixture(fixture)
    return fixtures


def validate_fixture(fixture: dict[str, Any]) -> None:
    required = {
        "name",
        "input_order",
        "units",
        "failure",
        "pre_state",
        "resume_deferred",
        "current_early_ack",
        "proposed_late_ack",
        "expected",
    }
    missing = required - fixture.keys()
    if missing:
        raise ValueError(f"{fixture.get('name')}: missing {sorted(missing)}")
    unit_names = [unit["sport"] for unit in fixture["units"]]
    if fixture["input_order"] != unit_names:
        raise ValueError(f"{fixture['name']}: input_order must match units")
    failure = fixture["failure"]
    if failure["kind"] not in FAILURE_KINDS:
        raise ValueError(f"{fixture['name']}: unknown failure kind")
    if failure.get("sport") is not None and failure["sport"] not in unit_names:
        raise ValueError(f"{fixture['name']}: failure sport is absent")
    for profile in ("current_early_ack", "proposed_late_ack"):
        if set(fixture[profile]) != {"redelivered", "lost_if_killed", "marker_policy"}:
            raise ValueError(f"{fixture['name']}: incomplete {profile} profile")
    expected_fields = {
        "committed_event_ids",
        "committed_snapshot_ids",
        "retry_cursor",
        "deferred_cursor",
        "redis_complete_sports",
        "terminal_counters",
        "duplicate_count",
        "sibling_outcome",
        "cleanup_observed",
    }
    if set(fixture["expected"]) != expected_fields:
        raise ValueError(f"{fixture['name']}: expected fields mismatch")


def _commit(state: State, unit: dict[str, Any]) -> None:
    # Idempotent upserts: a replay may attempt the same IDs but must not create
    # duplicate durable rows. The oracle counts durable duplicates, not attempts.
    state.events.update(unit["event_ids"])
    state.snapshots.update(unit["snapshot_ids"])


def simulate(fixture: dict[str, Any]) -> dict[str, Any]:
    validate_fixture(fixture)
    pre = fixture["pre_state"]
    state = State(
        events=set(pre["committed_event_ids"]),
        snapshots=set(pre["committed_snapshot_ids"]),
        markers=set(pre["redis_complete_sports"]),
    )
    units = {unit["sport"]: unit for unit in fixture["units"]}

    # A marker without durable rows is stale evidence, never a completion fact.
    for sport in list(state.markers):
        unit = units[sport]
        if not set(unit["event_ids"]).issubset(state.events):
            state.markers.remove(sport)
            state.marker_repairs.append(sport)
            state.retry_cursor.append(sport)

    failure = fixture["failure"]
    failed_sport = failure.get("sport")
    deferred: list[str] = []
    stop_after_failure = failure["kind"] == "hard_kill_between_units"

    for sport in fixture["input_order"]:
        unit = units[sport]
        kind = failure["kind"] if sport == failed_sport else "none"
        if kind in {"slow_odds", "hung_espn", "db_timeout_before_commit", "poison_event", "hard_kill_mid_unit"}:
            deferred.append(sport)
            state.retry_cursor.append(sport)
            if kind == "hard_kill_mid_unit":
                # A durable contract records all not-yet-started siblings too.
                index = fixture["input_order"].index(sport)
                siblings = fixture["input_order"][index + 1 :]
                deferred.extend(siblings)
                state.retry_cursor.extend(siblings)
                break
            continue

        _commit(state, unit)
        if kind == "redis_marker_failure":
            state.marker_repairs.append(sport)
        else:
            state.markers.add(sport)

        if kind == "db_timeout_after_commit":
            state.retry_cursor.append(sport)
        if stop_after_failure and sport == failed_sport:
            index = fixture["input_order"].index(sport)
            siblings = fixture["input_order"][index + 1 :]
            deferred.extend(siblings)
            state.retry_cursor.extend(siblings)
            break

    if failure["kind"] == "piggyback_failure":
        state.piggyback_failures = 1

    if fixture["resume_deferred"]:
        for sport in dict.fromkeys(state.retry_cursor + deferred):
            unit = units[sport]
            _commit(state, unit)
            state.markers.add(sport)
        deferred = []

    # Marker repair is independent from data replay and happens after durability.
    for sport in state.marker_repairs:
        unit = units[sport]
        if set(unit["event_ids"]).issubset(state.events):
            state.markers.add(sport)

    state.cleanup_observed = True
    failed_units = list(dict.fromkeys(deferred))
    state.failed_units = failed_units
    result = {
        "committed_event_ids": sorted(state.events),
        "committed_snapshot_ids": sorted(state.snapshots),
        "retry_cursor": list(dict.fromkeys(state.retry_cursor)),
        "deferred_cursor": failed_units,
        "redis_complete_sports": sorted(state.markers),
        "terminal_counters": {
            "committed_units": sum(
                set(unit["event_ids"]).issubset(state.events)
                for unit in fixture["units"]
            ),
            "deferred_units": len(failed_units),
            "failed_units": len(failed_units),
            "piggyback_failures": state.piggyback_failures,
            "marker_repairs": len(state.marker_repairs),
        },
        "duplicate_count": state.duplicate_writes,
        "sibling_outcome": "all_committed" if not failed_units else "survived_with_deferred",
        "cleanup_observed": state.cleanup_observed,
    }
    return result


def evaluate(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    fixtures = load_fixtures(path)
    failures = []
    for fixture in fixtures:
        actual = simulate(fixture)
        if actual != fixture["expected"]:
            failures.append({"name": fixture["name"], "expected": fixture["expected"], "actual": actual})
    return {"scenarios": len(fixtures), "passed": len(fixtures) - len(failures), "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_PATH)
    args = parser.parse_args()
    result = evaluate(args.fixtures)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
