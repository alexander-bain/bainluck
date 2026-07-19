"""Background task: refresh the live AI commentary box for THE OPEN CHAMPIONSHIP.

Same-day live feature (Alex, 2026-07-19). This is the ONLY place an OpenAI call is
made for the commentary box — the request path only reads the Redis key this task
writes (the house rule: never run LLM calls inside a GET).

Flow (every ``COMMENTARY_REFRESH_SECONDS``):
  1. Cheap Redis gate — skip immediately when no golf tournament window is active.
  2. Build The Open's event envelope via the SAME adapter the page uses
     (``GolfEventAdapter.build_event``), so liveness detection + fused live data
     are identical to what the page renders — no divergence.
  3. If the tournament is not live (upcoming/settled) or the envelope is missing,
     DELETE the Redis key (so the box stops rendering) and make NO OpenAI call.
  4. Otherwise generate strictly-grounded commentary and write it to Redis with a
     short TTL, so a stopped task self-clears the box rather than leaving it stale.

Best-effort throughout: any failure records a task failure via the wrapper but
never leaves a broken box (a missing/expired key simply renders no box).
"""

import json
import logging
from datetime import datetime, timezone

from app.utils.golf_commentary import (
    OPEN_SLUG,
    COMMENTARY_REFRESH_SECONDS,
    commentary_redis_key,
    generate_commentary,
    is_open_championship,
)

logger = logging.getLogger(__name__)

# TTL = 2x refresh, so if the beat stops the box disappears within one interval
# rather than showing a frozen blurb on a live page.
_COMMENTARY_TTL = COMMENTARY_REFRESH_SECONDS * 2


async def _refresh_open_commentary() -> dict:
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.tasks.datagolf import _golf_inplay_window_active
    from app.utils.event_concept import GolfEventAdapter

    rc = get_redis_client()
    key = commentary_redis_key(OPEN_SLUG)

    # 1) Cheap gate: off-tournament this is a single Redis read.
    if not _golf_inplay_window_active(rc):
        return {"skipped": "no_active_tournament_window"}

    # 2) Authoritative liveness + fused live data, straight from the page adapter.
    async with get_task_session() as db:
        envelope = await GolfEventAdapter().build_event(OPEN_SLUG, db)

    if not envelope:
        _safe_delete(rc, key)
        return {"skipped": "no_envelope"}

    event = envelope.get("event", {}) or {}
    name = event.get("name")
    status = event.get("status")

    # Defense-in-depth scope guard: the adapter is Open-only here, but never let a
    # slug/name mismatch generate for the wrong event.
    if not is_open_championship(OPEN_SLUG, name):
        _safe_delete(rc, key)
        return {"skipped": "not_open_championship"}

    # 3) LIVE-ONLY. Any non-live status clears the box and makes NO OpenAI call.
    if status != "live":
        _safe_delete(rc, key)
        return {"skipped": f"status_{status}"}

    competitors = (envelope.get("primary", {}) or {}).get("competitors", []) or []
    text = generate_commentary(name, competitors, status)
    if not text:
        # Generation unavailable/failed/insufficient data — do not touch the key.
        # An existing fresh blurb keeps rendering until it naturally expires; a
        # missing one simply stays absent (no broken/empty box).
        return {"skipped": "no_commentary_generated"}

    payload = json.dumps(
        {
            "text": text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": event.get("as_of"),
            "status": status,
        }
    )
    try:
        rc.setex(key, _COMMENTARY_TTL, payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to cache Open commentary: %s", exc)
        return {"error": "redis_write_failed"}

    return {"generated": True, "chars": len(text)}


def _safe_delete(rc, key: str) -> None:
    try:
        rc.delete(key)
    except Exception:
        pass
