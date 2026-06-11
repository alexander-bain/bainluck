"""Shared helpers for Discover feed response cache management."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

FEED_RESPONSE_CACHE_PREFIX = "feed_cache"
FEED_RESPONSE_STALE_TTL_SECONDS = 300


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
