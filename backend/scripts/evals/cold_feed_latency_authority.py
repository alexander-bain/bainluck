"""Pure C85 contracts for current cold-feed latency ownership and reuse."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).with_name("cold_feed_latency_authority_fixtures.json")


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


def response_cache_key(row: dict[str, Any]) -> str:
    raw = f"feed:anon:all:{row['limit']}:{row['offset']}:True:True::0.15:False:discover"
    return hashlib.md5(raw.encode()).hexdigest()


def candidate_base_key(row: dict[str, Any]) -> str:
    # Intentionally excludes response pagination and identity. Production must
    # include static sport/tag/config/version inputs when they differ.
    # v2 (Queue 288/C91): the live encoding was bumped when the identity became
    # collision-free (escaped delimiters, deduped/sorted tags, digest bound).
    # The anonymous default is unchanged apart from the version segment.
    return "discover-candidates:v2:all:no-static-tags"


def validate(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row["response_cache"] in {"hit", "stale_hit", "last_good"}:
        if row["runs_candidate_queries"] or row["build_owner"] != "none":
            errors.append("cached_response_rebuilds")
    if row["candidate_base"] == "hit" and row["runs_candidate_queries"]:
        errors.append("candidate_base_hit_requeries")
    if row["expected_candidate_base_reuse"] and row["candidate_base"] != "hit":
        errors.append("expected_base_reuse_missing")
    if row.get("build_quality") == "degraded" and row.get("publishes_response_cache", False):
        errors.append("degraded_response_published")
    if row.get("query_execution") == "serial_same_async_session" and row.get("parallel_safe"):
        errors.append("same_session_marked_parallel_safe")
    return errors


def main() -> int:
    corpus = load_fixture()
    print(json.dumps({
        "results": {row["id"]: validate(row) for row in corpus["scenarios"]},
        "response_keys": {row["id"]: response_cache_key(row) for row in corpus["scenarios"]},
        "candidate_keys": {row["id"]: candidate_base_key(row) for row in corpus["scenarios"]},
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
