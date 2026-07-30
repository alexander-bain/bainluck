"""Pure contract evaluator for the C82 calibration-integrity corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).with_name("calibration_population_integrity_fixtures.json")


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


def validate(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = row["expected"]
    domain = row["domain"]

    if domain == "resolution":
        if row.get("writes_winner") and expected.get("write") and not expected.get("stamp_source"):
            errors.append("winner_without_provenance")
        if row.get("transition") == "resolved_to_open" and not (
            expected.get("clear_winner") and expected.get("clear_source")
        ):
            errors.append("reopen_retains_grade")
        if row.get("incoming_source") == "price_buffer" and expected.get("calibration_eligible"):
            errors.append("price_self_grades")
    elif domain == "shape":
        if row["status"] == "resolved" and expected.get("write_shape"):
            if not (row.get("attended_recompute") and row.get("census_recorded") and row.get("version_bumped")):
                errors.append("unattended_resolved_shape_mutation")
    elif domain == "population":
        valid = bool(row.get("uses_canonical_ctes") and row.get("population_version"))
        if valid != expected["valid"]:
            errors.append("population_declaration_mismatch")
    elif domain == "liquidity":
        evidence = (row.get("yes_bid") or 0) > 0 or (row.get("last_price") or 0) > 0
        eligible = row["source"] != "kalshi" or evidence
        if eligible != expected["eligible"]:
            errors.append("liquidity_evidence_mismatch")
    elif domain == "grouping":
        grouped = bool(row.get("has_explicit_group_id") and row.get("relation") == "exactly_one")
        if grouped != expected["grouped"]:
            errors.append("group_identity_mismatch")
    elif domain == "source":
        if row.get("source_kind") == "model" and expected.get("published_curve"):
            errors.append("model_mixed_into_market_curve")
    elif domain == "cache":
        if row["origin"] == "redis_last_good" and not row["fresh_main_present"]:
            if expected.get("cache_status") != "stale" or not expected.get("memoized_copy_marked"):
                errors.append("stale_marker_not_memoized")
    else:
        errors.append("unknown_domain")
    return errors


def evaluate(corpus: dict[str, Any]) -> dict[str, list[str]]:
    return {row["id"]: validate(row, corpus) for row in corpus["scenarios"]}


def main() -> int:
    corpus = load_fixture()
    print(json.dumps(evaluate(corpus), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
