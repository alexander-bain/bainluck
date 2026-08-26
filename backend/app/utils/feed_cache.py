"""Shared helpers for Discover feed response cache management."""

from __future__ import annotations

import hashlib
import logging
import os
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

# --- #2216: live-awareness -----------------------------------------------------
# The principal TTLs above ask WHO is reading. They never ask WHAT the page
# contains, so a page holding an in-progress game aged exactly as long as a page
# of futures: 30-60s fresh, +300s on the stale mirror, and an UNBOUNDED
# process-local last-good behind that. Alex's push alert said 1-0 while both My
# Stuff cards said 0-0; the DB and ``GET /api/events/{id}`` both had 0-1. The
# write side was right and the page cache served an older payload as current.
#
# ``GET /api/events/{id}`` has never had this bug because it stores the event's
# status beside the payload and picks its TTL FROM that status
# (``routes/events.py:1841`` / ``:5771-5773``). These constants are that same
# rule for the card path, with the state read off the payload instead of a
# single row — a feed page is "live" when any card on it is.
#
# THE NUMBER, written down and defended: **60 seconds is the live ceiling** —
# the oldest a payload containing a live card may be and still be served.
#   * 30s fresh mirrors ``_EVENT_DETAIL_LIVE_TTL`` exactly. The detail route and
#     the card route read the SAME ORM fields; two different answers about the
#     same score is the defect, so they get one staleness rule.
#   * 60s on the stale mirror and on last-good is the actual fix. Fresh was
#     never the problem (30s); 30 + 300 = 330s, unbounded on a Redis blip, was.
#   * Past the ceiling the page is REBUILT, not served older. A five-minute-old
#     score printed as current is the app lying quietly, and the reliability bar
#     is "the app does what it's supposed to do".
# Anti-stampede is preserved by the per-key singleflight, not by the ceiling:
# waiters coalesce onto one leader, so refusing a stale live page costs one
# build per key per process, never a herd.
FEED_RESPONSE_TTL_LIVE_SECONDS = 30
FEED_RESPONSE_STALE_TTL_LIVE_SECONDS = 60
FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS = 60

# LAT-P089 operator kill switch for the inert-principal share.
FEED_INERT_PRINCIPAL_SHARE_ENV = "FEED_INERT_PRINCIPAL_SHARE"
_INERT_SHARE_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def inert_principal_share_enabled() -> bool:
    """Whether an inert principal may read the anonymous cache entry.

    ``FEED_INERT_PRINCIPAL_SHARE=0`` turns the LAT-P089 share off process-wide
    without a code change, mirroring ``FEED_SHARED_BUILD_TTL_S=0`` for #2143's
    module.

    It exists because the correctness argument, though sound, is an EQUALITY
    ARGUMENT — if some future field makes a personalized context compare equal
    to the default one, identified users start receiving anonymous content, and
    the only other remedy is a full deploy cycle. An operator lever must be
    faster than a release when the failure mode is "the wrong person's feed".

    Unset (the normal state) means ENABLED. Anything unrecognised also means
    enabled, deliberately: a typo'd config value must not silently switch off a
    latency fix and leave everyone wondering why the cold builds came back.
    """
    raw = os.environ.get(FEED_INERT_PRINCIPAL_SHARE_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _INERT_SHARE_OFF_VALUES


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


def payload_contains_live_event(payload: Any) -> bool:
    """Whether a built feed payload carries at least one live card (#2216).

    This is the feed's equivalent of the single ``event.status`` the detail
    route stores beside its cached response. A page is only as fresh as its
    fastest-moving card, so ONE live card makes the whole page live.

    Deliberately permissive in two ways, both toward freshness:

    * It does not filter on ``item["type"]``. Any card that declares itself
      ``status == "live"`` counts. A new card type that carries a live score
      should shorten the page's life on the day it ships, not on the day
      somebody remembers to add it to an allowlist here.
    * Anything it cannot parse — a non-dict payload, a missing or non-list
      ``items`` — returns ``False``, i.e. "not live", i.e. the ordinary TTL.
      That is the correct direction: this function only ever SHORTENS a TTL,
      so failing closed would mean a malformed payload silently gets the long
      one, while failing open would expire every unparseable page in 30s.

    Pure — no I/O, no clock. It is called on both the write and the read side
    precisely so the two cannot drift; the read path re-derives liveness from
    the payload rather than trusting a flag stamped into it, because a stamped
    flag can be dropped by any future serializer change without a test noticing.
    """
    if not isinstance(payload, dict):
        return False
    items = payload.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if isinstance(data, dict) and data.get("status") == "live":
            return True
    return False


def feed_response_cache_ttls(
    *,
    my_teams_only: bool = False,
    identified: bool = False,
    live: bool = False,
) -> tuple[int, int]:
    """``(fresh_ttl, stale_ttl)`` for one feed response cache entry (#2216).

    The principal rule (``feed_response_cache_ttl``) is unchanged and still
    decides the baseline. ``live=True`` then applies the live ceiling as a
    ``min``, never a replacement: the 5s identified TTL must stay 5s, because a
    live-aware ceiling that LENGTHENED anybody's cache would be a latency fix
    wearing a correctness fix's clothes.
    """
    fresh = feed_response_cache_ttl(
        my_teams_only=my_teams_only, identified=identified
    )
    stale = FEED_RESPONSE_STALE_TTL_SECONDS
    if live:
        fresh = min(fresh, FEED_RESPONSE_TTL_LIVE_SECONDS)
        stale = min(stale, FEED_RESPONSE_STALE_TTL_LIVE_SECONDS)
    return fresh, stale


def build_feed_cache_metadata(
    status: str,
    *,
    ttl_seconds: int | None = None,
    stale_ttl_seconds: int | None = FEED_RESPONSE_STALE_TTL_SECONDS,
    reason: str | None = None,
    live: bool | None = None,
) -> dict[str, Any]:
    """Return stable cache metadata safe to expose in feed responses.

    ``live`` (#2216) is emitted only when known, so an untouched caller's
    payload shape is byte-identical to before. It is the field that makes the
    ceiling verifiable from outside the process: ``.cache.live == true`` with
    ``.cache.ttl_seconds`` still at 60 would mean the live rule did not fire,
    and that is a distinction no amount of reading ``status`` can make.
    """
    metadata: dict[str, Any] = {
        "status": status,
    }
    if ttl_seconds is not None:
        metadata["ttl_seconds"] = ttl_seconds
    if stale_ttl_seconds is not None:
        metadata["stale_ttl_seconds"] = stale_ttl_seconds
    if reason:
        metadata["reason"] = reason
    if live is not None:
        metadata["live"] = bool(live)
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
