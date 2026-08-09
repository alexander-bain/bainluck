"""Canonical validator for the codex-owned eval registry (ruling 002)."""

from __future__ import annotations

from typing import Any


def validate(registry: dict[str, Any], changed: list[str] | None = None) -> dict[str, Any]:
    errors: set[str] = set()
    domains = registry.get("domains") or []
    known: dict[str, str] = {}
    relations: dict[str, str] = {}

    for domain in domains:
        domain_name = domain.get("domain")
        canonical = domain.get("canonical")
        if not domain_name or not canonical:
            errors.add("DOMAIN_INCOMPLETE")
            continue
        if canonical in known:
            errors.add("ARTIFACT_REGISTERED_TWICE")
        known[canonical] = domain_name
        for member in domain.get("members") or []:
            name = member.get("name")
            target = member.get("target")
            relation = member.get("relation")
            if not name or relation not in {"extends", "supersedes"}:
                errors.add("MEMBER_RELATION_INVALID")
                continue
            if name in known:
                errors.add("ARTIFACT_REGISTERED_TWICE")
            known[name] = domain_name
            if not target:
                errors.add("MEMBER_TARGET_MISSING")
            else:
                relations[name] = target

    for name, target in relations.items():
        if target not in known:
            errors.add("MEMBER_TARGET_UNKNOWN")
        elif known[target] != known[name]:
            errors.add("CROSS_DOMAIN_RELATION")

    for start in relations:
        seen: set[str] = set()
        node = start
        while node in relations:
            if node in seen:
                errors.add("RELATION_CYCLE")
                break
            seen.add(node)
            node = relations[node]

    for artifact in changed or []:
        if artifact not in known:
            errors.add("CHANGED_ARTIFACT_UNREGISTERED")

    return {"verdict": "ALLOW" if not errors else "REFUSE", "errors": sorted(errors)}
