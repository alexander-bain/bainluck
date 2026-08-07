"""Shared helpers for Discover feed response cache management."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

FEED_RESPONSE_CACHE_PREFIX = "feed_cache"
FEED_RESPONSE_STALE_TTL_SECONDS = 300

# LAT-P001: ASGI-scope marker that tells ``GET /api/feed`` to skip the response
# cache READ and genuinely rebuild. Lives in the scope (not a header/query param)
# precisely so no HTTP caller can set it — see the note at its use site.
FEED_PREWARM_SCOPE_KEY = "bainluck_feed_prewarm"

# Scope slot the route writes the RESOLVED cache key back into during a pre-warm,
# so the warmer publishes under the exact key the request path would read.
FEED_PREWARM_KEY_SCOPE_KEY = "bainluck_feed_prewarm_key"

# Response-cache TTLs by principal (see ``feed_response_cache_ttl``).
FEED_RESPONSE_TTL_ANON_SECONDS = 60
FEED_RESPONSE_TTL_IDENTIFIED_SECONDS = 5
FEED_RESPONSE_TTL_MY_TEAMS_SECONDS = 30


def feed_response_cache_key(
    *,
    user_id: Any = None,
    session_id: Optional[str] = None,
    sport: Optional[str] = None,
    limit: int,
    offset: int,
    include_events: bool = True,
    include_futures: bool = True,
    tags: Optional[str] = None,
    event_pct: Optional[float] = None,
    my_teams_only: bool = False,
    mode: Optional[str] = None,
) -> str:
    """Build the Redis response-cache key for one ``GET /api/feed`` shape.

    LAT-P001: this is the SINGLE source of truth for the key. It used to be an
    inline f-string in ``routes/feed.py``, which was fine while the request path
    was the only writer. The pre-warm beat is a second writer, and a warmer that
    computes the key even slightly differently warms a key nobody reads — it
    fails silently and looks exactly like a warmer that is working. Both callers
    now go through this function, and ``test_feed_prewarm.py`` pins that the
    warmed shapes equal the keys the route derives from the real request params.

    The principal segment mirrors the L2-242 shared-anon contract: an
    authenticated user and a session both get their own key; only a request with
    neither shares the ``anon`` key.
    """
    if user_id is not None:
        user_part = f"u:{user_id}"
    elif session_id:
        user_part = f"s:{session_id}"
    else:
        user_part = "anon"
    parts = (
        f"feed:{user_part}:{sport or 'all'}:{limit}:{offset}:"
        f"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:"
        f"{my_teams_only}:{mode or 'discover'}"
    )
    return f"{FEED_RESPONSE_CACHE_PREFIX}:{hashlib.md5(parts.encode()).hexdigest()}"


def feed_response_cache_ttl(
    *, my_teams_only: bool = False, identified: bool = False
) -> int:
    """Fresh-TTL for a feed response cache entry.

    Session/user feeds change as impressions are recorded, so they stay short.
    The anonymous key is deliberately the longest-lived: it is the one key a
    first-time visitor can hit, and it is the key the pre-warm beat keeps warm.
    """
    if my_teams_only:
        return FEED_RESPONSE_TTL_MY_TEAMS_SECONDS
    return (
        FEED_RESPONSE_TTL_IDENTIFIED_SECONDS
        if identified
        else FEED_RESPONSE_TTL_ANON_SECONDS
    )


def build_feed_cache_metadata(
    status: str,
    *,
    ttl_seconds: int | None = None,
    stale_ttl_seconds: int | None = FEED_RESPONSE_STALE_TTL_SECONDS,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return stable cache metadata safe to expose in feed responses."""
    metadata: dict[str, Any] = {
        "status": status,
    }
    if ttl_seconds is not None:
        metadata["ttl_seconds"] = ttl_seconds
    if stale_ttl_seconds is not None:
        metadata["stale_ttl_seconds"] = stale_ttl_seconds
    if reason:
        metadata["reason"] = reason
    return metadata


async def invalidate_feed_response_cache(reason: str) -> dict[str, Any]:
    """Delete cached Discover feed responses and stale fallbacks."""
    deleted = 0
    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        keys: list[Any] = []
        async for key in redis.scan_iter(
            match=f"{FEED_RESPONSE_CACHE_PREFIX}:*",
            count=100,
        ):
            keys.append(key)
            if len(keys) >= 100:
                deleted += await redis.delete(*keys) or 0
                keys = []
        if keys:
            deleted += await redis.delete(*keys) or 0
        await redis.aclose()
        return {"status": "ok", "deleted": deleted, "reason": reason}
    except Exception as exc:
        logger.warning("Failed to invalidate feed cache after %s: %s", reason, exc)
        return {"status": "error", "deleted": deleted, "reason": reason}
