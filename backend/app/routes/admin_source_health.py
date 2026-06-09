"""Source-level health dashboard — shows live status of every external data source."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/source-health", tags=["admin-source-health"])


def _check_admin_secret(secret: str) -> bool:
    import os
    return secret == os.getenv("ADMIN_TOKEN", os.getenv("ADMIN_SECRET", ""))


# Map each source to its primary task names for Redis metric lookups
_SOURCE_TASKS = {
    "odds_api": ["poll_all_odds", "discover_events"],
    "espn": ["espn_sync"],
    "statpal": ["statpal_livescores", "statpal_schedules"],
    "datagolf": ["datagolf_live", "poll_datagolf"],
    "kalshi": ["poll_kalshi"],
    "polymarket": ["poll_polymarket"],
    "mlb": ["mlb_sync"],
    "pexels": ["enrich_images"],
    "openai": ["enrich_hooks", "enrich_discover_llm"],
}

# DB queries to check freshness per source
_SOURCE_FRESHNESS_QUERIES = {
    "odds_api": "SELECT COUNT(*) FROM events WHERE updated_at > NOW() - INTERVAL '6 hours'",
    "espn": "SELECT COUNT(*) FROM events WHERE espn_id IS NOT NULL AND updated_at > NOW() - INTERVAL '6 hours'",
    "statpal": "SELECT COUNT(*) FROM events WHERE statpal_fixture_id IS NOT NULL AND updated_at > NOW() - INTERVAL '6 hours'",
    "kalshi": "SELECT COUNT(*) FROM futures_markets WHERE source = 'kalshi' AND updated_at > NOW() - INTERVAL '6 hours'",
    "polymarket": "SELECT COUNT(*) FROM futures_markets WHERE source = 'polymarket' AND updated_at > NOW() - INTERVAL '6 hours'",
    "datagolf": "SELECT COUNT(*) FROM futures_markets WHERE source = 'datagolf' AND updated_at > NOW() - INTERVAL '12 hours'",
}


@router.get("")
async def source_health(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Live health status for every external data source."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.redis_state import get_task_metrics, get_redis_client

    sources = {}
    alerts = []

    for source_name, task_names in _SOURCE_TASKS.items():
        task_metrics = []
        worst_health = "healthy"
        last_success = None
        total_failures_24h = 0
        max_consecutive = 0

        for tn in task_names:
            m = get_task_metrics(tn)
            task_metrics.append(m)

            health = m.get("health", "no_data")
            if health == "critical":
                worst_health = "critical"
            elif health == "degraded" and worst_health != "critical":
                worst_health = "degraded"
            elif health == "no_data" and worst_health == "healthy":
                worst_health = "no_data"

            ls = m.get("last_success_at")
            if ls and (last_success is None or ls > last_success):
                last_success = ls

            total_failures_24h += int(m.get("failures_24h", 0))
            max_consecutive = max(max_consecutive, int(m.get("consecutive_failures", 0)))

        # DB freshness check
        freshness_count = None
        if source_name in _SOURCE_FRESHNESS_QUERIES:
            try:
                result = await db.execute(text(_SOURCE_FRESHNESS_QUERIES[source_name]))
                freshness_count = result.scalar()
                if freshness_count == 0 and worst_health != "critical":
                    worst_health = "stale"
            except Exception:
                pass

        source_data = {
            "status": worst_health,
            "last_success_at": last_success,
            "failures_24h": total_failures_24h,
            "consecutive_failures": max_consecutive,
        }
        if freshness_count is not None:
            source_data["items_updated_6h"] = freshness_count

        if worst_health in ("critical", "stale"):
            alerts.append(f"{source_name}: {worst_health} (consecutive_failures={max_consecutive}, items_6h={freshness_count})")

        sources[source_name] = source_data

    # Quota info for Odds API
    try:
        rc = get_redis_client()
        remaining = rc.get("bainluck:odds_api_remaining")
        if remaining:
            sources["odds_api"]["quota_remaining"] = int(remaining.decode() if isinstance(remaining, bytes) else remaining)
        mode = rc.get("bainluck:circuit_breaker_mode")
        if mode:
            sources["odds_api"]["circuit_breaker"] = mode.decode() if isinstance(mode, bytes) else mode
    except Exception:
        pass

    overall = "healthy"
    if any(s["status"] == "critical" for s in sources.values()):
        overall = "critical"
    elif any(s["status"] in ("degraded", "stale") for s in sources.values()):
        overall = "degraded"

    return {
        "overall": overall,
        "sources": sources,
        "alerts": alerts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
