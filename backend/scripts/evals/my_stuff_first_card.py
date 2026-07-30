"""C88 My Stuff first-card, identity, and telemetry authority contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).with_name("my_stuff_first_card_fixtures.json")


def load_corpus() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text())


def decide(row: dict[str, Any]) -> dict[str, Any]:
    dispatch = row["dispatch_identity"]
    current = row["current_identity"]
    request = row["required_request"]
    same_principal = dispatch == current == row["cache_namespace"]

    if dispatch == "anon" and request == "not_started":
        return {"publish_required": False, "first_card": False, "prior_account_visible": False, "loading_clears": True, "outcome_class": "sign_in_required"}
    if not row["generation_match"]:
        outcome = "identity_superseded" if dispatch != current else "superseded"
        if request == "cancelled":
            outcome = "cancelled"
        return {"publish_required": False, "first_card": False, "prior_account_visible": False, "loading_clears": request == "cancelled", "outcome_class": outcome}
    if row["cache_hit"] and not same_principal:
        return {"publish_required": False, "first_card": False, "prior_account_visible": False, "loading_clears": False, "outcome_class": "cache_principal_mismatch"}
    if not row["view_active"] or request == "cancelled":
        return {"publish_required": False, "first_card": False, "prior_account_visible": False, "loading_clears": True, "outcome_class": "cancelled"}
    if request == "failure":
        return {"publish_required": False, "first_card": False, "prior_account_visible": False, "loading_clears": True, "outcome_class": "required_failure"}
    if request in {"success", "retry_success"}:
        count = int(row["required_item_count"])
        outcome = "memory_cache_hit" if row["cache_hit"] else request.replace("success", "network_success")
        if request == "retry_success":
            outcome = "retry_success"
        if count == 0:
            outcome = "empty_success"
        elif row["optional_request"] in {"failure", "hung"}:
            outcome = "partial_success"
        return {"publish_required": True, "first_card": count > 0, "prior_account_visible": False, "loading_clears": True, "outcome_class": outcome}
    raise ValueError(f"unhandled request state: {request}")


def validate_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    actual = decide(row)
    for key, expected in row["expected"].items():
        if actual[key] != expected:
            errors.append(f"decision_mismatch:{key}")
    if actual["first_card"] and int(row["required_item_count"]) <= 0:
        errors.append("first_card_without_content")
    if actual["publish_required"] and row["dispatch_identity"] != row["current_identity"]:
        errors.append("cross_identity_publication")
    if actual["first_card"] and not row["view_active"]:
        errors.append("first_card_after_navigation")
    return errors


def validate_telemetry(packet: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors = [f"missing:{field}" for field in corpus["required_telemetry"] if field not in packet]
    if packet.get("surface") != "my_stuff":
        errors.append("wrong_surface")
    forbidden = {"user_id", "email", "token", "item_ids", "market_text"}
    if forbidden & set(packet):
        errors.append("pii_or_content_in_telemetry")
    if packet.get("first_render_ms", -1) >= 0 and packet.get("item_count", 0) <= 0:
        errors.append("first_render_without_items")
    return errors


def main() -> int:
    corpus = load_corpus()
    result = {row["id"]: validate_row(row) for row in corpus["scenarios"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(any(result.values()))


if __name__ == "__main__":
    raise SystemExit(main())
