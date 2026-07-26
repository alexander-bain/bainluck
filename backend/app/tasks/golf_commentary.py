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

import asyncio
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

# ---------------------------------------------------------------------------
# Inner-operation timeouts (#1280).
#
# The task's Celery soft_time_limit is 60s (hard 90s). The two unbounded inner
# operations — the full golf aggregation (`build_event`) and the OpenAI call —
# each have to finish WELL below the soft limit so neither can push the task into
# SoftTimeLimitExceeded → hard-limit SIGKILL → prefork-pool corruption (the
# #1280 background-worker crash class). We bound EACH op, not just the loop
# boundary (the budget-guard-inner-op lesson), leaving headroom for cleanup:
#   build (25s) + generate (20s) + overhead ≈ 45s < 60s soft limit.
# On a breach the op is cancelled and the run degrades to an honest skip — never
# a raised soft-limit that retries and re-wedges the worker.
# ---------------------------------------------------------------------------
_BUILD_TIMEOUT_S = 25.0
_GENERATE_TIMEOUT_S = 20.0

# Eligibility self-suppression (#1280). The cheap `_golf_inplay_window_active`
# gate is GLOBAL — it is True whenever ANY golf tournament is live, so while an
# unrelated event (e.g. a regular PGA stop) is in play it let this beat run the
# full, expensive Open aggregation every 3 minutes even though The Open ended a
# week ago. Once a run determines The Open is not eligible (settled / absent /
# not-live), we cache that verdict for a bounded window and skip the expensive
# build entirely until it expires — turning the steady-state off-Open cost back
# into a single Redis GET while still re-checking periodically (self-healing if
# the tournament data flips back to live).
_OPEN_SUPPRESS_KEY = f"bainluck:golf_commentary:{OPEN_SLUG}:suppress"
_OPEN_SUPPRESS_TTL = 1800  # 30 min — bounded so a live flip is picked up promptly


async def _build_open_envelope() -> dict | None:
    """Build The Open's event envelope in its own session scope.

    Isolated so the whole DB interaction can be wrapped in a single
    ``asyncio.wait_for``: if the aggregation overruns, the cancellation unwinds
    the ``async with`` and closes the session cleanly (no leaked connection)."""
    from app.tasks.base import get_task_session
    from app.utils.event_concept import GolfEventAdapter

    async with get_task_session() as db:
        return await GolfEventAdapter().build_event(OPEN_SLUG, db)


async def _refresh_open_commentary() -> dict:
    from app.tasks.redis_state import get_redis_client
    from app.tasks.datagolf import _golf_inplay_window_active

    rc = get_redis_client()
    key = commentary_redis_key(OPEN_SLUG)

    # 1) Cheap gate: off-tournament this is a single Redis read.
    if not _golf_inplay_window_active(rc):
        return {"skipped": "no_active_tournament_window"}

    # 2) Cheap Open-specific gate: skip the expensive build while a recent run has
    # already determined The Open isn't eligible (settled/absent). Steady-state
    # off-Open cost is this one GET, not the full aggregation.
    if _open_suppressed(rc):
        return {"skipped": "open_not_eligible_cached"}

    # 3) Authoritative liveness + fused live data, straight from the page adapter,
    # BOUNDED so a slow aggregation degrades to a skip instead of hitting the
    # soft/hard time limit and SIGKILLing the worker (#1280).
    try:
        envelope = await asyncio.wait_for(
            _build_open_envelope(), timeout=_BUILD_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        # Do not clear the box or set the suppress latch: a transient slow build
        # is not proof the tournament is over. Report the degradation honestly.
        logger.warning(
            "Open commentary build_event exceeded %.0fs — degrading to skip",
            _BUILD_TIMEOUT_S,
        )
        return {"skipped": "build_timeout", "degraded": True}
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Open commentary build_event failed: %s", exc)
        return {"skipped": "build_error", "degraded": True}

    if not envelope:
        _safe_delete(rc, key)
        _suppress_open(rc)
        return {"skipped": "no_envelope"}

    event = envelope.get("event", {}) or {}
    name = event.get("name")
    status = event.get("status")

    # Defense-in-depth scope guard: the adapter is Open-only here, but never let a
    # slug/name mismatch generate for the wrong event.
    if not is_open_championship(OPEN_SLUG, name):
        _safe_delete(rc, key)
        _suppress_open(rc)
        return {"skipped": "not_open_championship"}

    # 4) LIVE-ONLY. Any non-live status clears the box, makes NO OpenAI call, and
    # latches the suppress verdict so we stop rebuilding until it expires.
    if status != "live":
        _safe_delete(rc, key)
        _suppress_open(rc)
        return {"skipped": f"status_{status}"}

    competitors = (envelope.get("primary", {}) or {}).get("competitors", []) or []

    # 5) Bounded generation. `generate_commentary` makes a synchronous OpenAI
    # call, so run it in a worker thread with a hard wait so a hung provider can
    # never block the event loop or approach the task soft limit. The OpenAI
    # client itself is separately bounded (timeout + limited retries) so the
    # orphaned thread also dies fast on a breach.
    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(generate_commentary, name, competitors, status),
            timeout=_GENERATE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Open commentary generation exceeded %.0fs — degrading to no box",
            _GENERATE_TIMEOUT_S,
        )
        return {"skipped": "commentary_timeout", "degraded": True}

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


def _open_suppressed(rc) -> bool:
    """True if a recent run already cached an 'Open not eligible' verdict."""
    try:
        return bool(rc.get(_OPEN_SUPPRESS_KEY))
    except Exception:
        # A Redis read hiccup must never wedge the beat — fall through to the
        # (bounded) build rather than silently skipping forever.
        return False


def _suppress_open(rc) -> None:
    """Latch 'Open not eligible' for a bounded window so the expensive build is
    skipped until it expires (self-healing re-check)."""
    try:
        rc.setex(_OPEN_SUPPRESS_KEY, _OPEN_SUPPRESS_TTL, "1")
    except Exception:
        pass


def _safe_delete(rc, key: str) -> None:
    try:
        rc.delete(key)
    except Exception:
        pass
