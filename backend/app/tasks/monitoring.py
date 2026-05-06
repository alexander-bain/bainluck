"""
Aggregation quality monitoring task.

Runs daily: samples live/recent events, logs source count and spread per event,
alerts when >20% are single-source. Stores results in Redis for admin dashboard.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

REDIS_KEY = "bainluck:aggregation_health"
REDIS_TTL = 86400 * 7  # 7 days


async def check_aggregation_quality():
    """Sample recent events, measure source diversity, store results."""
    from app.models.models import Event

    now = datetime.now(timezone.utc)
    stats = {
        "timestamp": now.isoformat(),
        "total_sampled": 0,
        "single_source": 0,
        "multi_source": 0,
        "zero_source": 0,
        "avg_source_count": 0.0,
        "source_distribution": {},
        "alert": False,
        "alert_reason": None,
    }

    async with get_task_session() as session:
        result = await session.execute(
            select(Event)
            .where(
                Event.status.in_(["live", "completed", "closed"]),
                Event.commence_time >= now - timedelta(hours=24),
            )
            .order_by(Event.commence_time.desc())
            .limit(50)
        )
        events = result.scalars().all()

        stats["total_sampled"] = len(events)
        source_counts = []
        source_names: dict[str, int] = {}

        for event in events:
            wp_sources = event.win_probability_sources or {}
            count = len(wp_sources)
            source_counts.append(count)

            if count == 0:
                stats["zero_source"] += 1
            elif count == 1:
                stats["single_source"] += 1
            else:
                stats["multi_source"] += 1

            for src in wp_sources:
                source_names[src] = source_names.get(src, 0) + 1

        if source_counts:
            stats["avg_source_count"] = round(sum(source_counts) / len(source_counts), 2)

        stats["source_distribution"] = source_names

        if stats["total_sampled"] > 0:
            single_pct = stats["single_source"] / stats["total_sampled"]
            if single_pct > 0.20:
                stats["alert"] = True
                stats["alert_reason"] = f"{single_pct:.0%} of events are single-source (threshold: 20%)"
                logger.warning("AGGREGATION ALERT: %s", stats["alert_reason"])

    if stats["alert"]:
        logger.warning("Aggregation quality: %s", json.dumps(stats, default=str))
    else:
        logger.info("Aggregation quality: %d events sampled, %.1f avg sources, %d single-source",
                     stats["total_sampled"], stats["avg_source_count"], stats["single_source"])

    try:
        from app.tasks.redis_state import get_redis_client
        r = get_redis_client()
        r.setex(REDIS_KEY, REDIS_TTL, json.dumps(stats, default=str))
    except Exception:
        pass

    return stats
