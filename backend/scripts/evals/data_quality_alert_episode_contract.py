"""Pure oracle for durable data-quality alert episode identity and lifecycle."""

from __future__ import annotations

import hashlib


def fingerprint(row: dict) -> str:
    parts = [str(row.get("check") or "unknown")]
    scope = row.get("scope") or "global"
    parts.append(str(scope))
    if scope == "event":
        parts.append(str(row.get("event_id") or "unknown-event"))
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:12]


def evaluate(row: dict) -> dict:
    reasons: list[str] = []
    state = row.get("state", "RED")
    board = row.get("board", "available")
    existing = row.get("existing", "none")

    if board == "unknown":
        action = "NO_OP_UNKNOWN"
        reasons.append("board_unknown")
    elif state == "GREEN":
        action = "CLOSE" if existing == "open" else "NO_OP_GREEN"
    elif existing == "open":
        action = "COMMENT"
    elif row.get("concurrent_claim") == "lost":
        action = "DEFER"
    else:
        action = "FILE"

    if row.get("dedup_source") == "redis_ttl":
        reasons.append("cooldown_not_durable_identity")
    if row.get("search_eventual"):
        reasons.append("eventual_search_not_authority")
    if row.get("marker_declared") is False and state == "RED":
        reasons.append("missing_canonical_marker")
    if row.get("duplicate_open_count", 0) > 1:
        reasons.append("historical_duplicates_need_canonical_oldest")

    return {"fingerprint": fingerprint(row), "action": action, "reason_codes": reasons}

