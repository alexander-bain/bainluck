"""Keep each published collection hub built ahead of its expiry. #9982.

SHIP: a reader who opens the NFL Week 4 collection sees the games right away,
including the first reader after a quiet spell. (Pillar: DISCOVER.)

## Why the request-path cache was not enough

``GET /api/containers/{slug}`` caches its body per (slug, revision) — fresh 60 s,
served stale to 300 s (30 s / 60 s while a game is live), see
``app.utils.container_read_cache``. Production 2026-10-02 00:3xZ, Week 4
(revision 34, 3,447 members): the first read **4.50 s** to first byte, the next
two 0.53 / 0.52 s. Week 4 went from revision 2 to 34 in ~19 h, so it is
republished about every 35 minutes, and each republish is a new key. A reader
who arrives more than five minutes after the last one, or after a republish,
pays the whole build — on Alex's iPhone (build 34) "very slow to open".

## What a pass does

For each hub Browse would offer (``discover_collections``, at most
:data:`MAX_HUBS`), read the published revision — the same read the route makes,
so the key matches the one a reader's request will look up — and rebuild the
shared (Redis) entry only when a reader could soon miss it:

* no entry for the current revision (never built, expired, or republished), or
* the entry is past ``fresh_until`` AND has under :data:`REFRESH_AHEAD_S` of
  servable life left.

A hub a reader rebuilt in the last fresh window is skipped, so with readers
present this adds nothing; the cost lands while the site is idle. The body is
built by the route's own builder and stored under the route's own key and
envelope — the hub a reader sees is byte-for-byte what the route would build.

Cadence: the beat fires every :data:`BEAT_PERIOD_S`. An idle non-live hub
(300 s of servable life) is rebuilt when under 150 s remain, so about every
2.5-3 minutes, never lapsing while passes arrive inside 150 s. A live hub's 60 s
life is shorter than one beat period, so a quiet live hub can still lapse between
passes; on live days readers keep it warm, and this does not try to.

Stated, not hidden: the beat is on ``background``, which delivers late (LAT-P112
measured p50 138-152 s against a declared 120 s, worst ~2,500 s). On-time
passes keep an idle hub warm; a delivery gap longer than ~150 s still lets the
next reader pay the build, as every reader did before this existed.
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Optional

from app.utils.container_read_cache import CachedRead, decode_entry, encode_entry

logger = logging.getLogger(__name__)

#: The beat's fire period (seconds). Mirrored by the beat entry; the wiring test
#: asserts the two agree.
BEAT_PERIOD_S = 60

#: Rebuild a stale entry with less servable life than this left. Must exceed
#: the beat period, or an idle hub lapses between two on-time passes.
REFRESH_AHEAD_S = 150

#: How many hubs a pass may build. The route's process-local tier holds 4.
MAX_HUBS = 4

#: Stop starting builds after this many seconds of a pass (one Week 4 build is
#: ~4-5 s; the task's soft limit is well above this).
PASS_BUDGET_S = 40.0


def container_hub_warmer_enabled() -> bool:
    """Kill switch, read at call time; ON unless set to ``false``."""
    return os.getenv("CONTAINER_HUB_WARMER_ENABLED", "true").strip().lower() != "false"


def needs_rebuild(entry: Optional[CachedRead], now: float) -> bool:
    """Would a reader soon pay the build for this key? Pure."""
    if entry is None or not entry.is_servable(now):
        return True
    if entry.is_fresh(now):
        return False
    return entry.stale_until - now < REFRESH_AHEAD_S


def _read_shared(client, key: str) -> Optional[CachedRead]:
    """The route's shared-tier entry for ``key``, or None. Fails open."""
    try:
        return decode_entry(client.get(key))
    except Exception:  # noqa: BLE001 — unreadable means "build it"
        logger.debug("container hub warmer: shared read failed", exc_info=True)
        return None


def _write_shared(client, key: str, entry: CachedRead) -> None:
    """Store ``entry`` exactly as the route's ``_publish_shared`` does.

    The SYNC client (``get_redis_client``, bounded): the route's process-shared
    async client is bound to the event loop that created it, and a worker runs
    each pass on its own loop, so reusing it would fail open on every pass after
    the first and the warmer would silently store nothing.
    """
    ttl = max(1, int(math.ceil(entry.stale_until - time.time())))
    client.set(key, encode_entry(entry), ex=ttl)


async def _warm_container_hubs() -> dict:
    """One pass. Returns a summary whose ``status`` is ``ok`` unless a build failed."""
    from app.routes.containers import _build_entry
    from app.tasks.redis_state import get_redis_client
    from app.services.container_discovery import discover_collections
    from app.services.database import async_session_maker
    from app.utils.container_corrections import READ_EMPTY, READ_PUBLISHED, read_published
    from app.utils.container_read_cache import (
        container_read_cache_enabled,
        container_read_cache_key,
    )

    summary: dict = {"status": "ok", "hubs": 0, "built": [], "skipped": [], "failed": []}
    if not container_hub_warmer_enabled() or not container_read_cache_enabled():
        summary["status"] = "disabled"
        return summary

    started = time.monotonic()
    client = get_redis_client()
    async with async_session_maker() as session:
        read = await discover_collections(session, limit=MAX_HUBS)
    slugs = [c.get("slug") for c in read.collections if isinstance(c, dict) and c.get("slug")]
    summary["hubs"] = len(slugs)

    for slug in slugs:
        if time.monotonic() - started > PASS_BUDGET_S:
            summary["status"] = "partial"
            break
        try:
            async with async_session_maker() as session:
                published = await read_published(session, slug)
                if published.state not in (READ_PUBLISHED, READ_EMPTY):
                    summary["skipped"].append(slug)
                    continue
                # `include_children=True` is the route's default, and what the
                # web hub and the iPhone both request.
                key = container_read_cache_key(slug, published.revision, True)
                if not needs_rebuild(_read_shared(client, key), time.time()):
                    summary["skipped"].append(slug)
                    continue
                fresh = await _build_entry(session, published, True)
            _write_shared(client, key, fresh)
            summary["built"].append(slug)
        except Exception:  # noqa: BLE001 — one hub never stops the others
            logger.warning("container hub warmer: build failed for %s", slug, exc_info=True)
            summary["failed"].append(slug)
            summary["status"] = "partial"
    summary["elapsed_s"] = round(time.monotonic() - started, 2)
    return summary
