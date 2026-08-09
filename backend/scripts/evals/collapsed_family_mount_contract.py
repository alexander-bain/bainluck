"""Contract for large collapsed families: reachable without eager child mounts."""

from __future__ import annotations

from typing import Any


def render_plan(groups: list[dict[str, Any]], open_keys: set[str], *, eager_limit: int = 24) -> dict[str, Any]:
    headers = []
    mounted = []
    reachable = []
    effects = 0
    for group in groups:
        key = str(group["key"])
        items = list(group.get("items", []))
        headers.append({"key": key, "count": len(items), "open": key in open_keys})
        reachable.extend(items)
        if key in open_keys or len(items) <= eager_limit:
            mounted.extend(items)
            effects += sum(int(item.get("effects", 0)) for item in items)
    return {
        "headers": headers,
        "reachable_ids": [item["id"] for item in reachable],
        "mounted_ids": [item["id"] for item in mounted],
        "mounted_effects": effects,
    }


def validate_plan(groups: list[dict[str, Any]], open_keys: set[str], plan: dict[str, Any], *, initial: bool) -> list[str]:
    reasons: list[str] = []
    all_ids = [item["id"] for group in groups for item in group.get("items", [])]
    if sorted(plan.get("reachable_ids", [])) != sorted(all_ids):
        reasons.append("ITEMS_NOT_REACHABLE")
    open_ids = [item["id"] for group in groups if str(group["key"]) in open_keys for item in group.get("items", [])]
    if not set(open_ids) <= set(plan.get("mounted_ids", [])):
        reasons.append("OPEN_GROUP_NOT_MOUNTED")
    if initial and not open_keys and len(all_ids) > 24 and plan.get("mounted_effects", 0) > 0:
        reasons.append("COLLAPSED_EFFECTS_EAGER")
    if initial and not open_keys and len(plan.get("mounted_ids", [])) > 24:
        reasons.append("COLLAPSED_DOM_EAGER")
    return reasons
