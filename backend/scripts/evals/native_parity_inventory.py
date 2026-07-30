"""Validate C87 native parity inventory and issue-dedup rules."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

INVENTORY_PATH = Path(__file__).with_name("native_parity_inventory.json")


def load_inventory() -> dict[str, Any]:
    return json.loads(INVENTORY_PATH.read_text())


def validate_capability(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "id", "journey", "dimension", "product_priority", "status",
        "action", "canonical_owner", "evidence", "reason",
    }
    missing = required - set(row)
    if missing:
        return [f"missing:{name}" for name in sorted(missing)]
    if row["status"] not in corpus["allowed_statuses"]:
        errors.append("invalid_status")
    if row["action"] not in corpus["allowed_actions"]:
        errors.append("invalid_action")
    if row["product_priority"] not in corpus["priority_order"]:
        errors.append("unknown_product_priority")
    if not row["evidence"]:
        errors.append("missing_evidence")
    if row["status"] == "confirmed" and not row["canonical_owner"]:
        errors.append("confirmed_gap_without_owner")
    if row["dimension"] == "optional-web-tooling" and row["status"] == "confirmed":
        errors.append("web_tooling_misclassified_as_native_defect")
    if row["action"] == "fix-now" and row["status"] != "confirmed":
        errors.append("fix_now_without_confirmed_gap")
    if row["action"] == "not-a-defect" and row["status"] not in {
        "refuted", "intentional-platform-difference"
    }:
        errors.append("not_a_defect_status_mismatch")
    return errors


def validate_inventory(corpus: dict[str, Any]) -> dict[str, list[str]]:
    rows = corpus["capabilities"]
    errors = {row["id"]: validate_capability(row, corpus) for row in rows}
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        errors["__inventory__"] = ["duplicate_capability_id"]
    packet_ids = [packet["id"] for packet in corpus.get("new_issue_packets", [])]
    if len(packet_ids) != len(set(packet_ids)):
        errors.setdefault("__inventory__", []).append("duplicate_issue_packet")
    return errors


def summary(corpus: dict[str, Any]) -> dict[str, Any]:
    rows = corpus["capabilities"]
    return {
        "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        "action_counts": dict(sorted(Counter(row["action"] for row in rows).items())),
        "fix_now": [row["id"] for row in rows if row["action"] == "fix-now"],
        "new_issue_packet_count": len(corpus.get("new_issue_packets", [])),
    }


def main() -> int:
    corpus = load_inventory()
    result = {"errors": validate_inventory(corpus), "summary": summary(corpus)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(any(result["errors"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
