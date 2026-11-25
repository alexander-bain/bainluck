"""L1 + L2 Redis cache for ``GET /api/events/{event_id}/nuggets`` (#13650).

Two requirements drive this store:
1. Sub-second repeat reads across workers without re-running expensive
   sub-surface queries.
2. Finished/closed games keep their ranked nuggets copy (7 days in Redis,
   surviving unrelated code deploys while gated by ``NUGGETS_SCHEMA_VERSION``)
   because settled game items no longer change.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

NUGGETS_CACHE_PREFIX = "bainluck:game_nuggets:v1:"
NUGGETS_SCHEMA_VERSION = "2026-11-24-v1"

FRESH_TTL_LIVE = 60
STALE_TTL_LIVE = 300
FRESH_TTL_FINAL = 604800  # 7 days
L1_MAX_SIZE = 128

_FINAL_STATUSES = frozenset({"completed", "closed"})

# event_id -> (stored_at_ts, is_final, build_id, full_payload)
_l1_cache: dict[int, tuple[float, bool, str, dict[str, Any]]] = {}
# sport_key -> (stored_at_ts, markets_list)
_season_markets_l1: dict[str, tuple[float, list[dict[str, Any]]]] = {}
SEASON_MARKETS_L1_TTL = 300


def _current_build_id() -> str:
    return (
        os.getenv("HEROKU_RELEASE_VERSION")
        or os.getenv("HEROKU_SLUG_COMMIT")
        or os.getenv("SOURCE_VERSION")
        or "local"
    )


def is_final_status(status: Any) -> bool:
    """Return True when an event status represents a settled/finished game."""
    return isinstance(status, str) and status.strip().lower() in _FINAL_STATUSES


def clear_l1() -> None:
    """Clear process-local L1 nuggets and season-market entries."""
    _l1_cache.clear()
    _season_markets_l1.clear()


def get_season_markets_l1(sport_key: str) -> Optional[list[dict[str, Any]]]:
    entry = _season_markets_l1.get(sport_key)
    if entry is None:
        return None
    stored_ts, markets = entry
    if (time.monotonic() - stored_ts) >= SEASON_MARKETS_L1_TTL:
        return None
    return markets


def set_season_markets_l1(sport_key: str, markets: list[dict[str, Any]]) -> None:
    _season_markets_l1[sport_key] = (time.monotonic(), markets)


def cache_key(event_id: int) -> str:
    return f"{NUGGETS_CACHE_PREFIX}{int(event_id)}"


def slice_nuggets_payload(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    """Return a shallow sliced copy of a full ``limit=12`` nuggets payload."""
    nuggets = list(payload.get("nuggets") or ())
    clamped = max(1, int(limit))
    sliced = nuggets[:clamped]
    out = dict(payload)
    out["nuggets"] = sliced
    out["first_eight_kinds"] = len(
        {item.get("kind") for item in sliced[:8] if isinstance(item, dict) and item.get("kind")}
    )
    return out


def _read_l1(event_id: int, *, is_final: bool, limit: int) -> Optional[dict[str, Any]]:
    entry = _l1_cache.get(int(event_id))
    if entry is None:
        return None
    stored_ts, cached_final, cached_build, payload = entry
    effective_final = is_final or cached_final
    ttl = FRESH_TTL_FINAL if effective_final else FRESH_TTL_LIVE
    if not effective_final and cached_build != _current_build_id():
        return None
    if (time.monotonic() - stored_ts) >= ttl:
        return None
    return slice_nuggets_payload(payload, limit)


def _write_l1(event_id: int, payload: dict[str, Any], *, is_final: bool) -> None:
    eid = int(event_id)
    if eid not in _l1_cache and len(_l1_cache) >= L1_MAX_SIZE:
        oldest = min(_l1_cache, key=lambda k: _l1_cache[k][0])
        _l1_cache.pop(oldest, None)
    _l1_cache[eid] = (time.monotonic(), is_final, _current_build_id(), payload)


def read(
    event_id: int,
    *,
    is_final: bool,
    limit: int = 12,
    rc=None,
) -> Optional[dict[str, Any]]:
    """Read cached nuggets payload from L1 or L2 Redis, slicing to ``limit``."""
    hit = _read_l1(event_id, is_final=is_final, limit=limit)
    if hit is not None:
        return hit

    try:
        if rc is None:
            from app.tasks.redis_state import get_redis_client

            rc = get_redis_client(fast_fail=True)
        raw = rc.get(cache_key(event_id))
        if not raw:
            return None
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        envelope = json.loads(text)
    except Exception:
        return None

    if not isinstance(envelope, dict):
        return None
    if envelope.get("schema_version") != NUGGETS_SCHEMA_VERSION:
        return None
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or "nuggets" not in payload:
        return None

    cached_final = bool(envelope.get("is_final")) or is_final
    if not cached_final and envelope.get("build_id") != _current_build_id():
        return None

    _write_l1(event_id, payload, is_final=cached_final)
    return slice_nuggets_payload(payload, limit)


def write(
    event_id: int,
    payload: dict[str, Any],
    *,
    is_final: bool,
    rc=None,
) -> bool:
    """Persist full ranked nuggets payload to L1 + Redis (7d finished, 60s live)."""
    if not isinstance(payload, dict) or "nuggets" not in payload:
        return False

    build_id = _current_build_id()
    _write_l1(event_id, payload, is_final=is_final)

    envelope = {
        "schema_version": NUGGETS_SCHEMA_VERSION,
        "build_id": build_id,
        "is_final": bool(is_final),
        "stored_at": int(time.time()),
        "payload": payload,
    }
    ttl = FRESH_TTL_FINAL if is_final else FRESH_TTL_LIVE
    try:
        if rc is None:
            from app.tasks.redis_state import get_redis_client

            rc = get_redis_client(fast_fail=True)
        serialized = json.dumps(envelope, separators=(",", ":"))
        rc.setex(cache_key(event_id), ttl, serialized)
        return True
    except Exception:
        return False
