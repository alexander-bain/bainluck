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
    """Build the golf response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.golf import get_golf

    async with get_task_session() as db:
        response = await get_golf(db)

    rc = get_redis_client()
    rc.set(f"{CACHE_PREFIX}golf", json.dumps(response, default=str), ex=CACHE_TTL)
    logger.info("Cached golf category page")
    return "ok"


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
