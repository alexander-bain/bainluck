"""Precompute category page responses and cache in Redis.

The politics, entertainment, economics, and weather endpoints query
FuturesMarket with eagerly-loaded outcomes, run classification/grouping,
and build cross-source comparisons. On production data volumes this
exceeds Heroku's 30-second request timeout.

This task runs every hour to pre-warm Redis caches.  The route handlers
read from cache first and only fall back to a live query when the cache
is missing.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Redis key prefix and TTL (2 hours — task runs every 1h, so there's overlap)
CACHE_PREFIX = "bainluck:category:"
CACHE_TTL = 7200
STALE_CACHE_TTL = 86400  # 24 hours — served when primary cache is cold


async def _precompute_politics():
    """Build the politics response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.politics import get_politics

    async with get_task_session() as db:
        response = await get_politics(db)

    rc = get_redis_client()
    rc.set(f"{CACHE_PREFIX}politics", json.dumps(response, default=str), ex=CACHE_TTL)
    logger.info("Cached politics category page (%d markets)", response.get("total_markets", 0))
    return response.get("total_markets", 0)


async def _precompute_entertainment():
    """Build the entertainment response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.entertainment import get_entertainment

    async with get_task_session() as db:
        response = await get_entertainment(db)

    rc = get_redis_client()
    payload = json.dumps(response, default=str)
    rc.set(f"{CACHE_PREFIX}entertainment", payload, ex=CACHE_TTL)
    rc.set(f"{CACHE_PREFIX}entertainment:stale", payload, ex=STALE_CACHE_TTL)
    logger.info("Cached entertainment category page (%d markets)", response.get("total_markets", 0))
    return response.get("total_markets", 0)


async def _precompute_economics():
    """Build the economics response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.economics import get_economics

    async with get_task_session() as db:
        response = await get_economics(db)

    rc = get_redis_client()
    payload = json.dumps(response, default=str)
    rc.set(f"{CACHE_PREFIX}economics", payload, ex=CACHE_TTL)
    rc.set(f"{CACHE_PREFIX}economics:stale", payload, ex=STALE_CACHE_TTL)
    logger.info("Cached economics category page (%d markets)", response.get("total_markets", 0))
    return response.get("total_markets", 0)


async def _precompute_weather():
    """Build all weather sub-endpoint responses and cache them."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.weather import (
        get_featured,
        get_cities,
        get_rain,
        get_events,
        get_climate,
        get_wildcards,
        get_cross_source,
    )

    async with get_task_session() as db:
        featured = await get_featured(db)
        cities = await get_cities(db)
        rain = await get_rain(db)
        events = await get_events(db)
        climate = await get_climate(db)
        wildcards = await get_wildcards(db)
        cross_source = await get_cross_source(db)

    rc = get_redis_client()
    for key, data in [
        ("weather:featured", featured),
        ("weather:cities", cities),
        ("weather:rain", rain),
        ("weather:events", events),
        ("weather:climate", climate),
        ("weather:wildcards", wildcards),
        ("weather:cross-source", cross_source),
    ]:
        rc.set(f"{CACHE_PREFIX}{key}", json.dumps(data, default=str), ex=CACHE_TTL)

    logger.info("Cached all 7 weather sub-endpoints")
    return 7


async def _precompute_golf():
    """Build the golf response and cache the category page + the feed base.

    In addition to the category-page cache, this publishes the user-independent
    golf listing *base* (Queue 278) so ``GET /api/feed`` reads it from Redis on
    process-cold rather than paying the ~8.9s inline ``get_golf`` rebuild
    (#1475/#1459). Keeping this on the worker means the web dyno never runs the
    heavy rebuild after a restart — Redis already holds a servable base.
    """
    from datetime import datetime, timezone
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.golf import get_golf
    from app.utils.golf_base import build_envelope, publish_envelope_sync

    async with get_task_session() as db:
        response = await get_golf(db)

    rc = get_redis_client()
    rc.set(f"{CACHE_PREFIX}golf", json.dumps(response, default=str), ex=CACHE_TTL)

    # Publish the freshness-tagged feed base (fresh + last-good keys).
    envelope = build_envelope(
        datetime.now(timezone.utc), response.get("tournaments", [])
    )
    publish_envelope_sync(rc, envelope)
    logger.info(
        "Cached golf category page + published feed base (%d tournaments)",
        len(envelope["tournaments"]),
    )
    return "ok"


async def _precompute_discover_candidate_base():
    """Precompute + publish the anonymous-default Discover candidate-ID base (Queue 285).

    Runs the exact ordered candidate-pool queries the feed uses
    (``feed._compute_ordered_candidate_ids`` — the same source both the request
    path and this task call) for the anonymous default key (``sport=None``,
    ``static_tag_filter=None``) and publishes the user-independent ordered ID list
    as a versioned, freshness-tagged envelope. ``GET /api/feed`` then reads this
    on a cold response-cache key instead of re-running the ~3–6s nine-query
    discovery, so page one and page two of the same anonymous scroll (and native's
    50/200 shapes) reuse one base.

    Contracts honoured:

    * **Kill switch** — when the Redis ``discover_candidate_base:enabled`` key is
      ``"0"`` the build is skipped entirely (the feed also ignores the base and
      runs direct queries).
    * **Failed/partial builds never replace last-good** — the envelope is
      published ONLY when the build produced a non-empty, valid ID list within the
      deadline. An empty/invalid/timed-out build leaves the prior last-good key
      untouched.
    * **Measured** — build wall time and per-pool DB row counts are logged.
    * **Bounded** — the build is deadline-guarded so it can never run long.

    Only the anonymous default key is beat-warmed; arbitrary sport/static-tag feed
    requests populate their own correctly-keyed base on first request (or fall
    back to direct queries), per ``candidate_base.get_candidate_base``.
    """
    import asyncio
    import os
    import time
    from datetime import datetime, timezone

    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.feed import _compute_ordered_candidate_ids
    from app.utils.candidate_base import (
        CANDIDATE_BASE_ENABLED_KEY,
        base_identity,
        build_envelope,
        payload_valid,
        publish_candidate_base_sync,
    )

    rc = get_redis_client()

    # Kill switch — skip the build (and DB load) entirely when disabled.
    try:
        raw_enabled = rc.get(CANDIDATE_BASE_ENABLED_KEY)
        if raw_enabled is not None:
            value = (
                raw_enabled.decode()
                if isinstance(raw_enabled, (bytes, bytearray))
                else raw_enabled
            )
            if str(value).strip() == "0":
                logger.info("Discover candidate base precompute skipped — kill switch off")
                return "disabled"
    except Exception:
        logger.debug("candidate base kill-switch read failed", exc_info=True)

    try:
        deadline_s = float(os.getenv("CANDIDATE_BASE_BUILD_DEADLINE_S", "20"))
    except (TypeError, ValueError):
        deadline_s = 20.0

    now = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        async with get_task_session() as db:
            market_ids, pool_counts, curator_ids = await asyncio.wait_for(
                _compute_ordered_candidate_ids(db, now, None, None),
                timeout=deadline_s,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Discover candidate base build exceeded %.0fs deadline — keeping last-good",
            deadline_s,
        )
        return "timeout"
    build_ms = round((time.perf_counter() - t0) * 1000, 1)

    identity = base_identity(None, None)
    envelope = build_envelope(
        now,
        identity,
        market_ids,
        pool_counts=pool_counts,
        external_curator_recall_ids=curator_ids,
    )

    # Failed/partial builds never replace last-good: only publish a fully-built,
    # non-empty, valid envelope.
    if not market_ids or not payload_valid(envelope, expected_identity=identity):
        logger.warning(
            "Discover candidate base build empty/invalid (%d ids, %.1fms) — keeping last-good",
            len(market_ids),
            build_ms,
        )
        return "empty"

    publish_candidate_base_sync(rc, envelope)
    logger.info(
        "Published Discover candidate base (%d ids, pools=%s, build=%.1fms)",
        len(market_ids),
        pool_counts,
        build_ms,
    )
    return len(market_ids)


async def _precompute_grids():
    """Pre-warm championship grid caches for MLB, NBA, NHL, Golf.

    #901: golf was missing from this warm list, so `/playoffs/golf` read an
    unwarmed `bainluck:category:playoffs:golf` key on every load → cold rebuild
    via ~15 sequential DataGolf calls (~12s) and frequent skeleton stalls. Golf
    is warmed here so the request path hits Redis like the other leagues.
    """
    from app.tasks.base import get_task_session
    from app.routes.playoffs import get_playoff_grid
    from app.tasks.redis_state import get_redis_client
    import asyncio

    rc = get_redis_client()
    warmed = []
    for slug in ["mlb", "nba", "nhl", "golf"]:
        try:
            async with get_task_session() as session:
                result = await asyncio.wait_for(
                    get_playoff_grid(slug, hours=None, top=10, debug=False, db=session),
                    timeout=120,
                )
                payload = json.dumps(result, default=str)
                cache_key = f"bainluck:category:playoffs:{slug}"
                rc.setex(cache_key, 3600, payload)
                rc.setex(f"{cache_key}:stale", 86400, payload)
                warmed.append(slug)
        except Exception:
            logger.exception("Failed to precompute %s grid", slug)
    return warmed


async def _precompute_all_category_pages():
    """Precompute all category page caches."""
    results = {}
    for name, fn in [
        ("politics", _precompute_politics),
        ("entertainment", _precompute_entertainment),
        ("economics", _precompute_economics),
        ("weather", _precompute_weather),
        ("golf", _precompute_golf),
        ("grids", _precompute_grids),
    ]:
        try:
            results[name] = await fn()
        except Exception:
            logger.exception("Failed to precompute %s category page", name)
            results[name] = "error"

    logger.info("Category page precompute complete: %s", results)
    return {"status": "ok", "results": results}
