"""C86 four-axis Discover staleness authority and metric contract."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).with_name("discover_staleness_authority_fixtures.json")
REQUIRED_METRIC_METADATA = {
    "deployed_sha",
    "generated_at",
    "cache_status",
    "build_quality",
    "limit",
    "offset",
    "surface",
    "client_shape",
    "fixture_version",
}


def load_corpus() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text())


def classify(row: dict[str, Any]) -> dict[str, Any]:
    lifecycle = row["lifecycle"]
    content = row["content"]
    user = row["user_recency"]
    cache = row["cache"]

    if not lifecycle.get("correction_reopen"):
        if lifecycle.get("status") in {"resolved", "closed"}:
            return {"authoritative_stale": True, "surface": False, "reason": "status_terminal"}
        if lifecycle.get("resolution_relation") == "past":
            return {"authoritative_stale": True, "surface": False, "reason": "past_resolution"}
        if lifecycle.get("linked_event") == "completed_current":
            return {"authoritative_stale": True, "surface": False, "reason": "linked_event_completed"}

    if content.get("title_time") == "explicit_past":
        return {"authoritative_stale": False, "surface": False, "reason": "title_date_elapsed"}
    if content.get("recurring_calendar") == "correct_elapsed":
        return {"authoritative_stale": False, "surface": False, "reason": "recurring_calendar_elapsed"}
    if content.get("updated_age_hours", 0) > 48 and not content.get("fresh_movement"):
        return {"authoritative_stale": False, "surface": False, "reason": "stale_without_movement"}
    if content.get("empty_envelope"):
        return {"authoritative_stale": False, "surface": False, "reason": "empty_envelope"}
    if content.get("duplicate_family"):
        return {"authoritative_stale": False, "surface": False, "reason": "duplicate_family"}
    if user.get("dismissed"):
        return {"authoritative_stale": False, "surface": False, "reason": "dismissed"}

    reason = "eligible"
    if user.get("seen_age_hours") is not None:
        reason = "eligible_recycled"
    if cache.get("status") == "stale_hit":
        reason = "eligible_cache_stale"
    return {"authoritative_stale": False, "surface": True, "reason": reason}


def validate_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for axis in ("lifecycle", "content", "user_recency", "cache"):
        if axis not in row:
            errors.append(f"missing_axis:{axis}")
    if errors:
        return errors
    actual = classify(row)
    for key in ("authoritative_stale", "surface", "reason"):
        if actual[key] != row["expected"][key]:
            errors.append(f"decision_mismatch:{key}")
    if row["content"].get("leader_probability") is not None and row["expected"]["reason"] == "status_terminal":
        if row["lifecycle"]["status"] == "open" and row["lifecycle"]["resolution_relation"] != "past":
            errors.append("price_used_as_lifecycle_authority")
    if row["cache"].get("status") == "stale_hit" and row["expected"]["authoritative_stale"]:
        lifecycle = row["lifecycle"]
        if lifecycle.get("status") == "open" and lifecycle.get("resolution_relation") != "past":
            errors.append("cache_age_used_as_lifecycle_authority")
    return errors


def stale_metric(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_METRIC_METADATA - set(metadata))
    if missing:
        raise ValueError(f"missing metric metadata: {', '.join(missing)}")
    renderable = [row for row in rows if row["expected"]["surface"]]
    stale = [row for row in renderable if row["expected"]["authoritative_stale"]]
    reasons = Counter(row["expected"]["reason"] for row in stale)
    limit = int(metadata["limit"])
    denominator = min(limit, len(renderable))
    return {
        "metric": f"authoritative-stale-rate@{limit}",
        "numerator": len(stale[:limit]),
        "denominator": denominator,
        "rate": len(stale[:limit]) / denominator if denominator else 0.0,
        "root_causes": dict(sorted(reasons.items())),
        "metadata": metadata,
    }


def main() -> int:
    corpus = load_corpus()
    result = {row["id"]: validate_row(row) for row in corpus["scenarios"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(any(result.values()))


if __name__ == "__main__":
    raise SystemExit(main())
