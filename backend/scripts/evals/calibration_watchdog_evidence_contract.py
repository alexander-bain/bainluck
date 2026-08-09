"""Oracle for selecting bounded, actionable calibration watchdog context."""

from __future__ import annotations

from typing import Any


FAILED = {"cancelled", "failed", "timeout"}
DIAGNOSTIC_PREFIXES = ("staged:cursor_",)


def _duration(value: Any) -> int | None:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def current_query_selection(payload: dict[str, Any], limit: int = 10) -> list[str]:
    """Model CAL-P023 SQL: all non-complete phases, then stages by cost."""
    rows: list[tuple[int, int, str]] = []
    for phase in payload.get("phases") or []:
        if phase.get("status") not in {"complete", "resumed"}:
            rows.append((0, 0, f"phase:{phase.get('name')}:{phase.get('status')}"))
    for name, raw in (payload.get("stages") or {}).items():
        duration = _duration(raw)
        # The SQL bigint cast aborts the whole context query on malformed data.
        if duration is None:
            return []
        rows.append((1, -duration, f"stage:{name}"))
    return [row[2] for row in sorted(rows)[:limit]]


def select_evidence(payload: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    """Keep actual failures, decisive cursor evidence, then costly stages."""
    reasons: set[str] = set()
    selected: list[str] = []
    phases = payload.get("phases")
    stages = payload.get("stages")
    if not isinstance(phases, list):
        phases = []
        reasons.add("PHASES_MISSING")
    if not isinstance(stages, dict):
        stages = {}
        reasons.add("STAGES_MISSING")

    for phase in phases:
        if not isinstance(phase, dict):
            reasons.add("MALFORMED_PHASE")
            continue
        if phase.get("status") in FAILED:
            selected.append(f"phase:{phase.get('name')}:{phase.get('status')}")

    parsed: list[tuple[str, int]] = []
    for name, raw in stages.items():
        duration = _duration(raw)
        if duration is None:
            reasons.add("MALFORMED_STAGE_DURATION")
            continue
        parsed.append((str(name), duration))

    decisive = sorted(
        ((name, cost) for name, cost in parsed if name.startswith(DIAGNOSTIC_PREFIXES)),
        key=lambda pair: pair[0],
    )
    costly = sorted(
        ((name, cost) for name, cost in parsed if not name.startswith(DIAGNOSTIC_PREFIXES)),
        key=lambda pair: (-pair[1], pair[0]),
    )
    for name, _ in decisive + costly:
        item = f"stage:{name}"
        if item not in selected and len(selected) < limit:
            selected.append(item)

    if not selected:
        reasons.add("NO_ACTIONABLE_CONTEXT")
    return {"selected": selected[:limit], "reasons": sorted(reasons)}
