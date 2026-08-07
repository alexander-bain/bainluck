"""Dependency-free oracle for anonymous feed pre-warm and decay behavior."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/feed_prewarm_decay_contract.json"


def load_corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def evaluate_case(case: dict) -> dict:
    kind = case["kind"]
    data = case["input"]
    if kind == "shape":
        warmed = (
            data["principal"] == "anon"
            and data["limit"] == 20
            and data["offset"] == 0
            and data.get("sport") is None
            and data.get("tags") is None
            and data.get("include_events", True)
            and data.get("include_futures", True)
            and not data.get("my_teams_only", False)
            and (
                (data.get("mode") in (None, "discover") and data.get("event_pct") == 0.15)
                or (data.get("mode") == "sports" and data.get("event_pct") is None)
            )
        )
        result = {"warmed": warmed, "visitor_state": "hit" if warmed else "cold_build"}
    elif kind == "beat_death":
        age = data["age_seconds"]
        if age <= data["fresh_ttl_seconds"]:
            state = "hit"
        elif age <= data["stale_ttl_seconds"]:
            state = "stale_hit"
        else:
            state = "cold_build"
        result = {"visitor_state": state, "age_disclosed": data["age_disclosed"]}
    elif kind == "redis_failure":
        state = "last_good" if data["process_last_good"] else "cold_or_unavailable"
        result = {
            "visitor_state": state,
            "age_bounded": data["last_good_max_age_seconds"] is not None,
            "age_disclosed": data["age_disclosed"],
        }
    elif kind == "warmer_result":
        publishable = (
            data["build_quality"] == "complete"
            and data["item_count"] > 0
            and data["resolved_key"]
        )
        if not publishable:
            outcome = "refuse_publish"
        elif not data["fresh_write_ok"] or not data["stale_write_ok"]:
            outcome = "raises"
        else:
            outcome = "published"
        result = {"outcome": outcome, "second_shape_attempted": not data.get("abort_loop", False)}
    elif kind == "key":
        fields = (
            "principal", "sport", "limit", "offset", "include_events", "include_futures",
            "tags", "event_pct", "my_teams_only", "mode",
        )
        result = {"keys_equal": all(data["warmer"].get(f) == data["route"].get(f) for f in fields)}
    else:
        raise ValueError(kind)
    return result


def evaluate_corpus(corpus: dict) -> dict:
    rows = []
    for case in corpus["cases"]:
        actual = evaluate_case(case)
        rows.append({"id": case["id"], "passed": actual == case["expected"], "actual": actual})
    return {"total": len(rows), "passed": sum(r["passed"] for r in rows), "cases": rows}


if __name__ == "__main__":
    print(json.dumps(evaluate_corpus(load_corpus()), indent=2, sort_keys=True))
