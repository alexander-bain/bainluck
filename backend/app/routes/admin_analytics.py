"""Admin analytics endpoints powered by GA4 Data API.

All endpoints require the admin secret and cache responses in Redis
to avoid hammering the GA4 API on repeated loads.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.routes.admin_utils import _check_admin_secret

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Redis cache helpers
# ---------------------------------------------------------------------------

_CACHE_PREFIX = "bainluck:analytics"


async def _cache_get(key: str) -> dict | list | None:
    """Read a JSON-serialised value from Redis."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        raw = await rc.get(f"{_CACHE_PREFIX}:{key}")
        await rc.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("Redis cache miss/error for %s", key)
    return None


async def _cache_set(key: str, data: Any, ttl_seconds: int) -> None:
    """Write a JSON-serialised value to Redis with a TTL."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        await rc.setex(f"{_CACHE_PREFIX}:{key}", ttl_seconds, json.dumps(data, default=str))
        await rc.aclose()
    except Exception:
        logger.debug("Redis cache write error for %s", key)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

CACHE_TTL_STANDARD = 3600  # 1 hour
CACHE_TTL_REALTIME = 300   # 5 minutes


@router.get("/analytics/overview")
async def analytics_overview(
    secret: str = Query(..., description="Admin secret"),
    period: str = Query("7d", description="Period: 7d or 30d"),
):
    """Key site metrics: DAU, sessions, avg session duration, bounce rate, top pages."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    cache_key = f"overview:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import get_engagement_metrics, get_top_pages

    start_date = "7daysAgo" if period == "7d" else "30daysAgo"

    try:
        engagement = get_engagement_metrics(start_date=start_date, end_date="today")
        top_pages = get_top_pages(start_date=start_date, end_date="today", limit=25)
    except Exception as exc:
        logger.error("GA4 overview query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    result = {
        "period": period,
        "engagement": engagement,
        "topPages": top_pages,
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/discover")
async def analytics_discover(
    secret: str = Query(..., description="Admin secret"),
    period: str = Query("7d", description="Period: 7d or 30d"),
):
    """Discover-specific metrics: feed loads, card events, scroll depth, H/L plays."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    cache_key = f"discover:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import run_report

    start_date = "7daysAgo" if period == "7d" else "30daysAgo"

    try:
        # Discover page views
        discover_pages = run_report(
            dimensions=["pagePath"],
            metrics=["screenPageViews", "activeUsers", "averageSessionDuration"],
            start_date=start_date,
            end_date="today",
            limit=50,
            order_by_metric="screenPageViews",
        )
        # Filter to Discover-related paths
        discover_paths = [
            r for r in discover_pages
            if any(p in r.get("pagePath", "") for p in ["/discover", "/", "/sports"])
        ]

        # Custom events: feed interactions, H/L plays, scroll depth
        events_data = run_report(
            dimensions=["eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=100,
            order_by_metric="eventCount",
        )
        # Filter to Discover-relevant events
        discover_event_names = {
            "page_view", "scroll", "feed_card_click", "feed_card_view",
            "higher_lower_play", "higher_lower_result", "discover_swipe",
            "discover_card_click", "discover_scroll_depth",
            "engagement_time", "session_start", "first_visit",
        }
        discover_events = [
            r for r in events_data
            if r.get("eventName", "") in discover_event_names
            or r.get("eventName", "").startswith("discover_")
            or r.get("eventName", "").startswith("higher_lower_")
        ]

        # Daily trend for feed loads
        daily_feed = run_report(
            dimensions=["date"],
            metrics=["screenPageViews", "activeUsers"],
            start_date=start_date,
            end_date="today",
            limit=90,
        )
    except Exception as exc:
        logger.error("GA4 Discover query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    result = {
        "period": period,
        "discoverPages": discover_paths,
        "discoverEvents": discover_events,
        "dailyTrend": daily_feed,
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/realtime")
async def analytics_realtime(
    secret: str = Query(..., description="Admin secret"),
):
    """Current active users and top active pages."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    cache_key = "realtime"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import get_realtime

    try:
        result = get_realtime()
    except Exception as exc:
        logger.error("GA4 realtime query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    await _cache_set(cache_key, result, CACHE_TTL_REALTIME)
    return result


@router.get("/analytics/retention")
async def analytics_retention(
    secret: str = Query(..., description="Admin secret"),
    period: str = Query("30d", description="Period: 7d, 30d, or 90d"),
):
    """Daily/weekly retention cohorts: new vs returning users."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    cache_key = f"retention:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import get_user_retention

    period_map = {"7d": "7daysAgo", "30d": "30daysAgo", "90d": "90daysAgo"}
    start_date = period_map.get(period, "30daysAgo")

    try:
        raw_data = get_user_retention(start_date=start_date, end_date="today")
    except Exception as exc:
        logger.error("GA4 retention query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    # Reshape into daily buckets with new/returning split
    daily: dict[str, dict[str, Any]] = {}
    for row in raw_data:
        date = row.get("date", "")
        segment = row.get("newVsReturning", "unknown")
        users = int(row.get("activeUsers", 0))
        sessions = int(row.get("sessions", 0))

        if date not in daily:
            daily[date] = {"date": date, "new": 0, "returning": 0, "newSessions": 0, "returningSessions": 0}
        if segment == "new":
            daily[date]["new"] = users
            daily[date]["newSessions"] = sessions
        elif segment == "returning":
            daily[date]["returning"] = users
            daily[date]["returningSessions"] = sessions

    sorted_daily = sorted(daily.values(), key=lambda d: d["date"])

    # Compute summary
    total_new = sum(d["new"] for d in sorted_daily)
    total_returning = sum(d["returning"] for d in sorted_daily)
    total_all = total_new + total_returning
    retention_rate = round(total_returning / total_all * 100, 1) if total_all else 0

    result = {
        "period": period,
        "summary": {
            "totalNewUsers": total_new,
            "totalReturningUsers": total_returning,
            "retentionRate": retention_rate,
        },
        "daily": sorted_daily,
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result
