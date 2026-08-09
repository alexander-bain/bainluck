"""Authority for end-to-end first-real-content latency packets."""

from __future__ import annotations

import math
from typing import Any


ALLOWED_CACHE = {"hit", "miss", "stale_hit", "last_good", "disabled", "unknown"}
REAL_CONTENT = {"discover_card", "sports_card", "politics_market", "search_result", "golf_market"}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def evaluate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    required = {"trace_id", "surface", "request_started_ms", "response_received_ms", "first_content_ms", "content_kind", "cache_status", "backend_elapsed_ms", "attempts", "timeout_ms", "server_stages"}
    if required - set(packet):
        return {"verdict": "REFUSE", "reasons": ["FIELDS_MISSING"]}
    trace = packet.get("trace_id")
    if not isinstance(trace, str) or not trace or len(trace) > 64 or any(ch in trace for ch in "@/ "):
        reasons.add("TRACE_ID_INVALID")
    if any(key in packet for key in ("session_id", "user_id", "token", "query", "response_body")):
        reasons.add("PRIVACY_FIELD_PRESENT")

    times = [packet.get("request_started_ms"), packet.get("response_received_ms"), packet.get("first_content_ms")]
    if not all(_number(value) for value in times):
        reasons.add("TIMELINE_INVALID")
    elif not times[0] <= times[1] <= times[2]:
        reasons.add("TIMELINE_INVALID")
    if packet.get("content_kind") not in REAL_CONTENT or packet.get("mounted") is not True or not packet.get("stable_content_id"):
        reasons.add("FIRST_CONTENT_NOT_PROVEN")
    if packet.get("cache_status") not in ALLOWED_CACHE:
        reasons.add("CACHE_STATUS_INVALID")
    if not _number(packet.get("backend_elapsed_ms")):
        reasons.add("BACKEND_DURATION_INVALID")

    stages = packet.get("server_stages")
    if not isinstance(stages, dict):
        reasons.add("SERVER_STAGES_INVALID")
        stages = {}
    elif any(not isinstance(name, str) or not name or not _number(value) for name, value in stages.items()):
        reasons.add("SERVER_STAGES_INVALID")
    elif stages and sum(stages.values()) > packet.get("backend_elapsed_ms", 0) * 1.05:
        reasons.add("SERVER_STAGES_EXCEED_BACKEND")

    attempts = packet.get("attempts")
    if not isinstance(attempts, int) or attempts < 1:
        reasons.add("ATTEMPT_ACCOUNTING_INVALID")
    elif attempts > 1 and not packet.get("retry_durations_ms"):
        reasons.add("RETRY_ACCOUNTING_MISSING")
    retry = packet.get("retry_durations_ms") or []
    if not isinstance(retry, list) or any(not _number(value) for value in retry):
        reasons.add("RETRY_ACCOUNTING_INVALID")
    if packet.get("timed_out") and not _number(packet.get("timeout_ms")):
        reasons.add("TIMEOUT_BOUND_MISSING")

    attribution = None
    if not reasons:
        total = times[2] - times[0]
        network_and_queue = max(0, times[1] - times[0] - packet["backend_elapsed_ms"])
        client_to_content = times[2] - times[1]
        attribution = {
            "total_ms": total,
            "backend_ms": packet["backend_elapsed_ms"],
            "network_and_queue_ms": network_and_queue,
            "client_to_content_ms": client_to_content,
        }
    return {"verdict": "ATTRIBUTABLE" if not reasons else "REFUSE", "reasons": sorted(reasons), "attribution": attribution}
