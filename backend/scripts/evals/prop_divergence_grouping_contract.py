"""Independent render-plan oracle for grouped prop divergence sections."""

from __future__ import annotations

from typing import Any


def _family(key: Any) -> str | None:
    if not isinstance(key, str) or "|" not in key:
        return None
    family = key.split("|", 1)[0].strip()
    return family or None


def _movement(row: dict[str, Any]) -> float | None:
    before, current = row.get("pregame_mark"), row.get("current")
    if not isinstance(before, (int, float)) or not isinstance(current, (int, float)):
        return None
    return abs(current - before)


def render_plan(case: dict[str, Any]) -> dict[str, Any]:
    state = case["state"]
    rows = list(case.get("items") or [])
    reasons: set[str] = set()
    if len({str(row.get("key")) for row in rows}) != len(rows):
        reasons.add("DUPLICATE_RENDER_KEY")

    ranked = sorted(
        enumerate(rows),
        key=lambda pair: (
            _movement(pair[1]) is None,
            -(_movement(pair[1]) or 0),
            pair[0],
        ),
    ) if state == "divergence" else list(enumerate(rows))

    groups: list[dict[str, Any]] = []
    by_name: dict[str | None, dict[str, Any]] = {}
    for _, row in ranked:
        name = _family(row.get("key"))
        if name not in by_name:
            by_name[name] = {"name": name, "visible": [], "collapsed": []}
            groups.append(by_name[name])
        movement = _movement(row)
        collapsible = (
            state == "divergence"
            and not row.get("settled")
            and movement is not None
            and round((row["current"] - row["pregame_mark"]) * 100) == 0
        )
        target = "collapsed" if collapsible else "visible"
        by_name[name][target].append(row["id"])

    flattened = [item for group in groups for item in group["visible"] + group["collapsed"]]
    if sorted(flattened) != sorted(row["id"] for row in rows):
        reasons.add("ROW_RETENTION_DRIFT")
    if state == "divergence":
        rendered_movements = [
            _movement(next(row for row in rows if row["id"] == item))
            for group in groups for item in group["visible"] + group["collapsed"]
        ]
        known = [value for value in rendered_movements if value is not None]
        if known != sorted(known, reverse=True):
            reasons.add("GLOBAL_DIVERGENCE_ORDER_DRIFT")
    return {"verdict": "ALLOW" if not reasons else "REFUSE", "reasons": sorted(reasons), "groups": groups}
