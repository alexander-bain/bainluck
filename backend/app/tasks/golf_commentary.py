"""Background task: refresh the live AI commentary box for THE OPEN CHAMPIONSHIP.

Same-day live feature (Alex, 2026-07-19). This is the ONLY place an OpenAI call is
made for the commentary box — the request path only reads the Redis key this task
writes (the house rule: never run LLM calls inside a GET).

The box is a CHANGE-DETECTOR, not a status readout: each run snapshots the whole
event state (leaderboard + every prop market) to Redis and diffs against the
previous run, so the update reports WHAT JUST MOVED — and, where a golfer's
scoring change lines up with a market move, ties them together ("as X birdied the
17th, the U.S. region-to-win rose 40%->42%").

Flow (every ``COMMENTARY_REFRESH_SECONDS``):
  1. Cheap Redis gate — skip immediately when no golf tournament window is active.
  2. Build The Open's envelope via the SAME adapter the page uses
     (``GolfEventAdapter.build_event``) — identical liveness + fused live data.
  3. Not live / no envelope -> DELETE the commentary key (box stops rendering),
     NO OpenAI call.
  4. Snapshot current state; diff vs the previous snapshot.
     - New moves -> generate the 'what just moved' digest, write it.
     - Quiet stretch (prev exists, nothing moved) -> NO OpenAI call; just refresh
       the existing blurb's TTL so it stays visible.
     - First run (no prev) -> seed a current-state summary.
  5. Always store the current snapshot as the next diff baseline.

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
    state_redis_key,
    snapshot_state,
    diff_state,
    has_new_moves,
    generate_from_snapshots,
    is_open_championship,
)

logger = logging.getLogger(__name__)

# TTL = 2x refresh, so if the beat stops the box disappears within one interval
# rather than showing a frozen blurb on a live page.
_COMMENTARY_TTL = COMMENTARY_REFRESH_SECONDS * 2
# The previous-state snapshot only needs to outlive one interval to be diffable.
_STATE_TTL = COMMENTARY_REFRESH_SECONDS * 3


async def _refresh_open_commentary() -> dict:
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.tasks.datagolf import _golf_inplay_window_active
    from app.utils.event_concept import GolfEventAdapter

    rc = get_redis_client()
    key = commentary_redis_key(OPEN_SLUG)
    skey = state_redis_key(OPEN_SLUG)

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
        _safe_delete(rc, skey)
        return {"skipped": f"status_{status}"}

    competitors = (envelope.get("primary", {}) or {}).get("competitors", []) or []

    # 4) Snapshot current state and diff against the previous run.
    cur = snapshot_state(envelope)
    cur["ts"] = datetime.now(timezone.utc).isoformat()
    prev = _safe_get_json(rc, skey)

    # Persist the current snapshot as the next diff baseline regardless of outcome.
    _safe_set_json(rc, skey, cur, _STATE_TTL)

    diff = diff_state(prev, cur)

    # 4a) Quiet stretch (we have a baseline but nothing moved): do NOT spend an
    # OpenAI call. Refresh the existing blurb's TTL so the last update stays
    # visible on the live page rather than expiring during a lull.
    if prev is not None and not has_new_moves(diff):
        refreshed = _refresh_ttl(rc, key)
        return {"skipped": "no_moves", "kept_blurb": refreshed}

    # 4b) New moves (or first run) -> generate the digest.
    text = generate_from_snapshots(name, cur, prev, status, competitors)
    if not text:
        # Generation unavailable/failed/insufficient data — leave the key untouched
        # (existing blurb keeps rendering until it expires; absent stays absent).
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

    return {
        "generated": True,
        "chars": len(text),
        "scoring_moves": len(diff.get("scoring") or []),
        "prop_moves": len(diff.get("props") or []),
        "first_run": prev is None,
    }


def _safe_delete(rc, key: str) -> None:
    try:
        rc.delete(key)
    except Exception:
        pass


def _safe_get_json(rc, key: str):
    try:
        raw = rc.get(key)
        if raw:
            return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception:
        pass
    return None


def _safe_set_json(rc, key: str, obj, ttl: int) -> None:
    try:
        rc.setex(key, ttl, json.dumps(obj, default=str))
    except Exception:
        pass


def _refresh_ttl(rc, key: str) -> bool:
    """Re-write the existing commentary blurb with a fresh TTL (no OpenAI call), so
    a quiet stretch doesn't let the last update expire off the live page. Returns
    False when there is no blurb to keep."""
    try:
        raw = rc.get(key)
        if not raw:
            return False
        rc.setex(key, _COMMENTARY_TTL, raw)
        return True
    except Exception:
        return False
