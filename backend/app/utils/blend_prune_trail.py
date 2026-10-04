"""Durable per-event trail of blend-source prunes (#9051).

The matcher drops a kalshi/polymarket key from ``Event.win_probability_sources``
when no linked market of that source remains. #9051 logs each prune, but the
heavy app has no log drain: a line lives ~3 minutes in Heroku's buffer, so a
held-page frame that shows a source missing 20 minutes later cannot be paired
with the prune that caused it.

This trail keeps the attribution where the reader can still find it:
``bainluck:blend_prune_trail:{event_id}`` holds a JSON list (oldest first) of
``{"at", "source", "phase", "committed"}``, capped and expiring after 72h.
Read it with ``GET /api/admin/redis-read?key=bainluck:blend_prune_trail:<id>``.

``committed`` is the honest half. ``phase="cleanup"`` records are written only
after that helper's own commit, so they say True. ``phase="unlink"`` records are
written where the UPDATE is staged; the caller commits later and may roll back,
so they say False and prove nothing about removal on their own.

Best-effort: a Redis failure is swallowed and never changes the prune.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TRAIL_KEY_PREFIX = "bainluck:blend_prune_trail:"
TRAIL_MAX = 50
TRAIL_TTL_S = 72 * 3600


def trail_key(event_id: int) -> str:
    return f"{TRAIL_KEY_PREFIX}{int(event_id)}"


def append_record(existing: list | None, record: dict, cap: int = TRAIL_MAX) -> list:
    """Pure: append ``record`` and keep only the newest ``cap`` entries."""
    trail = list(existing) if isinstance(existing, list) else []
    trail.append(record)
    return trail[-cap:]


def record_blend_prune(
    event_id: int, source: str, phase: str, committed: bool, client=None
) -> bool:
    """Append one prune to the event's trail. Returns True when written."""
    try:
        if client is None:
            from app.tasks.redis_state import get_redis_client

            client = get_redis_client()
        key = trail_key(event_id)
        raw = client.get(key)
        try:
            existing = json.loads(raw) if raw else []
        except Exception:
            existing = []  # A corrupt trail is replaced, never allowed to block.
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "phase": phase,
            "committed": bool(committed),
        }
        client.setex(key, TRAIL_TTL_S, json.dumps(append_record(existing, record)))
        return True
    except Exception as exc:
        try:
            logger.warning("blend prune trail: write failed event_id=%s: %s", event_id, exc)
        except Exception:
            pass
        return False
