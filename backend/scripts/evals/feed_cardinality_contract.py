"""Pure C83 feed-cardinality and concept-envelope contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CARDINALITY_FIXTURES = ROOT / "feed_cardinality_fixtures.json"
CONCEPT_FIXTURES = ROOT / "concept_envelope_authority_fixtures.json"


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_cardinality(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row["cache_key_limit"] != row["limit"]:
        errors.append("limit_not_in_cache_identity")
    if row.get("degraded_reason") and row["build_quality"] == "complete":
        errors.append("degraded_reason_on_complete")
    degraded = row["build_quality"] != "complete" or bool(row.get("degraded_reason"))
    if degraded and (row["cache_fresh_written"] or row["cache_stale_written"]):
        errors.append("degraded_cached")
    expected_returned = max(0, min(row["limit"], row["total"] - row["offset"]))
    if row["returned"] != expected_returned:
        errors.append("pagination_count_mismatch")
    if row["stage_counts"]["bundles"] != row["total"]:
        errors.append("final_stage_total_mismatch")
    return errors


def validate_concept(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = row["expected"]
    hub_complete = all(row.get(k) for k in ("key", "name", "domain"))
    if row["presentation"] == "prediction":
        content = bool(row.get("probabilities")) or bool(row.get("winner"))
        surface = hub_complete and content
    elif row["presentation"] == "navigation_hub":
        surface = hub_complete and (row.get("entry_count", 0) > 0 or row.get("fight_count", 0) > 0)
    else:
        surface = False
    if surface != expected["surface"]:
        errors.append("surface_decision_mismatch")

    live = bool(
        row.get("status") == "live"
        and row.get("start_authority") in {"calendar", "provider_schedule"}
        and row.get("start_relation") == "past"
        and row.get("end_relation", "future") != "past"
    )
    if live != expected["live"]:
        errors.append("live_authority_mismatch")
    return errors


def main() -> int:
    cardinality = load_fixture(CARDINALITY_FIXTURES)
    concepts = load_fixture(CONCEPT_FIXTURES)
    print(json.dumps({
        "cardinality": {r["id"]: validate_cardinality(r) for r in cardinality["scenarios"]},
        "concepts": {r["id"]: validate_concept(r) for r in concepts["scenarios"]},
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
