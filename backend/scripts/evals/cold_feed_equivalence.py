"""Offline equivalence contracts for cold-feed golf and futures changes.

The oracle is intentionally independent of application code. Implementing queues
can run it before and after a refactor to freeze cache freshness, ownership,
ordered candidate union, thin-pool merge, and telemetry namespace semantics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
GOLF_FIXTURES = ROOT / "golf_base_cache_fixtures.json"
FUTURES_FIXTURES = ROOT / "futures_pool_equivalence_fixtures.json"
GOLF_FRESH_SECONDS = 300
GOLF_FORBIDDEN_TOP_LEVEL = {
    "feed_tours",
    "personalized",
    "personalization",
    "final_rank",
}
GOLF_FORBIDDEN_TOURNAMENT = {
    "score",
    "reason",
    "headline",
    "personalized",
    "final_rank",
    "_marquee_pin",
}


def _load(path: Path, kind: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1 or payload.get("kind") != kind:
        raise ValueError(f"unsupported {kind} fixture schema")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError(f"{kind} fixtures must be a non-empty list")
    names = [fixture.get("name") for fixture in fixtures]
    if any(not isinstance(name, str) or not name for name in names):
        raise ValueError(f"{kind} fixture names must be non-empty strings")
    if len(names) != len(set(names)):
        raise ValueError(f"{kind} fixture names must be unique")
    return fixtures


def load_golf_fixtures(path: Path = GOLF_FIXTURES) -> list[dict[str, Any]]:
    fixtures = _load(path, "golf_base_cache")
    for fixture in fixtures:
        required = {
            "name",
            "primary",
            "last_good",
            "inline_fallback",
            "ownership_events",
            "expected",
        }
        if set(fixture) != required:
            raise ValueError(f"{fixture['name']}: golf fields mismatch")
    return fixtures


def load_futures_fixtures(path: Path = FUTURES_FIXTURES) -> list[dict[str, Any]]:
    fixtures = _load(path, "futures_pool_equivalence")
    for fixture in fixtures:
        required = {
            "name",
            "pool_order",
            "pools",
            "orm_rows",
            "canonical_counts",
            "interestingness",
            "primary_items",
            "relaxed_items",
            "relaxed_outcome",
            "timings",
            "expected",
        }
        if set(fixture) != required:
            raise ValueError(f"{fixture['name']}: futures fields mismatch")
        if set(fixture["pool_order"]) != set(fixture["pools"]):
            raise ValueError(f"{fixture['name']}: pool order/pool keys differ")
    return fixtures


def golf_payload_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if GOLF_FORBIDDEN_TOP_LEVEL.intersection(payload):
        return False
    tournaments = payload.get("tournaments")
    if not isinstance(tournaments, list):
        return False
    for tournament in tournaments:
        if not isinstance(tournament, dict):
            return False
        if GOLF_FORBIDDEN_TOURNAMENT.intersection(tournament):
            return False
        required = {
            "key",
            "golfers",
            "market_ids",
            "market_sources",
            "h2h_matchups",
            "prop_markets",
            "schedule_status",
        }
        if not required.issubset(tournament):
            return False
    return True


def _usable_cache(entry: dict[str, Any], max_age_s: int) -> bool:
    return (
        entry.get("status") == "ok"
        and isinstance(entry.get("age_s"), (int, float))
        and 0 <= entry["age_s"] <= max_age_s
        and golf_payload_valid(entry.get("payload"))
    )


def select_golf_base(fixture: dict[str, Any]) -> dict[str, Any]:
    primary = fixture["primary"]
    last_good = fixture["last_good"]
    fallback = fixture["inline_fallback"]
    if _usable_cache(primary, GOLF_FRESH_SECONDS):
        return {"action": "serve_primary", "payload": primary["payload"]}
    if _usable_cache(last_good, int(last_good.get("max_age_s", GOLF_FRESH_SECONDS))):
        return {"action": "serve_last_good", "payload": last_good["payload"]}
    if fallback.get("status") == "success" and golf_payload_valid(fallback.get("payload")):
        return {"action": "serve_inline", "payload": fallback["payload"]}
    return {"action": "unavailable", "payload": None}


def simulate_golf_ownership(events: list[dict[str, str]]) -> dict[str, Any]:
    owner: str | None = None
    waiters: list[str] = []
    launches: list[str] = []
    actions: list[str] = []
    for event in events:
        actor = event["actor"]
        operation = event["op"]
        if operation == "claim":
            if owner is None:
                owner = actor
                launches.append(actor)
                actions.append(f"{actor}:owner")
            else:
                if actor not in waiters:
                    waiters.append(actor)
                actions.append(f"{actor}:wait:{owner}")
        elif operation in {"cancel", "fail", "complete"}:
            if actor != owner:
                actions.append(f"{actor}:ignored_non_owner_{operation}")
                continue
            actions.append(f"{actor}:{operation}")
            owner = None
        else:
            raise ValueError(f"unknown ownership operation: {operation}")
    return {
        "launches": launches,
        "actions": actions,
        "owner": owner,
        "waiters": waiters,
        "slot_clean": owner is None,
    }


def ordered_candidate_ids(fixture: dict[str, Any]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for pool_name in fixture["pool_order"]:
        pool = fixture["pools"][pool_name]
        for row in pool["rows"][: int(pool["limit"])]:
            market_id = int(row["id"])
            if market_id not in seen:
                seen.add(market_id)
                ordered.append(market_id)
    return ordered


def restore_orm_order(candidate_ids: list[int], rows: list[dict[str, Any]]) -> list[int]:
    by_id = {int(row["id"]): row for row in rows}
    return [market_id for market_id in candidate_ids if market_id in by_id]


def joined_market_order(fixture: dict[str, Any], market_ids: list[int]) -> list[dict[str, Any]]:
    canonical = fixture["canonical_counts"]
    interestingness = fixture["interestingness"]
    return [
        {
            "id": market_id,
            "canonical_count": canonical.get(str(market_id)),
            "interestingness": interestingness.get(str(market_id)),
        }
        for market_id in market_ids
    ]


def merge_thin_items(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    primary = [dict(item) for item in fixture["primary_items"]]
    if fixture["relaxed_outcome"] in {"timeout", "cancelled"}:
        return primary
    seen = {item["id"] for item in primary}
    for item in fixture["relaxed_items"]:
        if item["id"] not in seen:
            primary.append(dict(item))
            seen.add(item["id"])
    return primary


def validate_timing_contract(fixture: dict[str, Any]) -> dict[str, Any]:
    timings = fixture["timings"]
    primary = timings.get("primary", {})
    relaxed = timings.get("relaxed", {})
    names_separate = all(key.startswith("futures.") for key in primary) and all(
        key.startswith("futures.relaxed.") for key in relaxed
    )
    child_sum = sum(primary.values()) + sum(relaxed.values())
    parent_ms = timings.get("parent_ms", 0)
    # candidate_queries overlaps pool children and is excluded from the additive
    # child sum used for explainability.
    non_overlapping_sum = sum(
        value
        for key, value in {**primary, **relaxed}.items()
        if not key.endswith("candidate_queries")
    )
    return {
        "thin_pass": bool(relaxed),
        "names_separate": names_separate,
        "raw_child_sum": child_sum,
        "non_overlapping_sum": non_overlapping_sum,
        "parent_covers_non_overlapping": parent_ms >= non_overlapping_sum,
    }


def evaluate_golf(path: Path = GOLF_FIXTURES) -> dict[str, Any]:
    failures = []
    fixtures = load_golf_fixtures(path)
    for fixture in fixtures:
        actual = {
            "selection": select_golf_base(fixture),
            "ownership": simulate_golf_ownership(fixture["ownership_events"]),
        }
        if actual != fixture["expected"]:
            failures.append({"name": fixture["name"], "expected": fixture["expected"], "actual": actual})
    return {"scenarios": len(fixtures), "passed": len(fixtures) - len(failures), "failures": failures}


def evaluate_futures(path: Path = FUTURES_FIXTURES) -> dict[str, Any]:
    failures = []
    fixtures = load_futures_fixtures(path)
    for fixture in fixtures:
        candidate_ids = ordered_candidate_ids(fixture)
        restored = restore_orm_order(candidate_ids, fixture["orm_rows"])
        actual = {
            "candidate_ids": candidate_ids,
            "restored_ids": restored,
            "joined": joined_market_order(fixture, restored),
            "merged_items": merge_thin_items(fixture),
            "timing_contract": validate_timing_contract(fixture),
        }
        if actual != fixture["expected"]:
            failures.append({"name": fixture["name"], "expected": fixture["expected"], "actual": actual})
    return {"scenarios": len(fixtures), "passed": len(fixtures) - len(failures), "failures": failures}


def evaluate() -> dict[str, Any]:
    golf = evaluate_golf()
    futures = evaluate_futures()
    return {
        "golf": golf,
        "futures": futures,
        "passed": not golf["failures"] and not futures["failures"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = evaluate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
