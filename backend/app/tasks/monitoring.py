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


async def check_tier1_event_coverage():
    """Alert when Tier 1 Kalshi game markets exist without matching events.

    Checks unlinked Kalshi game tickers for NBA/NHL/MLB/NFL with ticker dates
    within 36 hours. Any gap means a fan could open a game page and not see
    Kalshi data because the event doesn't exist yet.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func, or_
    from app.tasks.base import get_task_session
    from app.models.models import FuturesMarket
    from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    _TIER1_PREFIXES = [
        p for p in KALSHI_GAME_TICKER_PREFIXES
        if any(p.startswith(s) for s in ("kxnba", "kxnhl", "kxmlb", "kxnfl"))
    ]
    # Only check moneyline tickers (kx{sport}game) to avoid counting
    # spread/total/prop duplicates for the same game
    _GAME_ONLY = [p for p in _TIER1_PREFIXES if "game" in p]

    now = datetime.now(timezone.utc)
    alerts = []

    async with get_task_session() as session:
        ticker_conditions = [
            func.lower(FuturesMarket.external_id).like(f"{p}%")
            for p in _GAME_ONLY
        ]
        result = await session.execute(
            select(FuturesMarket.external_id, FuturesMarket.name)
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status == "open",
                or_(*ticker_conditions),
            )
        )
        unlinked = result.all()

        for row in unlinked:
            game_date = extract_game_date_from_ticker(row.external_id)
            if not game_date:
                continue
            hours_until = (game_date - now).total_seconds() / 3600
            if -6 < hours_until < 36:
                alerts.append({
                    "ticker": row.external_id,
                    "name": row.name,
                    "game_date": game_date.isoformat(),
                    "hours_until": round(hours_until, 1),
                })

    if alerts:
        logger.warning(
            "TIER 1 EVENT GAP: %d Kalshi game markets within 36h have no matching event: %s",
            len(alerts),
            ", ".join(a["ticker"][:30] for a in alerts[:5]),
        )

    return {
        "tier1_gaps": len(alerts),
        "alerts": alerts,
    }


SNAPSHOT_DIST_KEY = "bainluck:snapshot_distribution"
SNAPSHOT_DIST_TTL = 86400  # 24h


async def compute_snapshot_distribution_impl():
    """Compute snapshot count distribution per source for open markets.

    Samples 200 most-recent markets per source, counts snapshots for each
    outcome. Writes result to Redis. Designed to run as a Celery task
    (too slow for a web request due to 90M-row snapshot table).
    """
    from sqlalchemy import text
    from app.tasks.redis_state import get_redis

    async with get_task_session() as session:
        sources_result = (await session.execute(text(
            "SELECT DISTINCT source FROM futures_markets WHERE status IN ('open', 'active')"
        ))).all()

        all_sources = []
        for source_row in sources_result:
            src = source_row.source

            sample = (await session.execute(text("""
                WITH sample_markets AS (
                    SELECT id FROM futures_markets
                    WHERE source = :src AND status IN ('open', 'active')
                    ORDER BY id DESC LIMIT 200
                ),
                outcome_snaps AS (
                    SELECT fo.id,
                           (SELECT COUNT(*) FROM futures_odds_snapshots fos
                            WHERE fos.outcome_id = fo.id) AS snap_count
                    FROM futures_outcomes fo
                    WHERE fo.market_id IN (SELECT id FROM sample_markets)
                )
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE snap_count = 0) AS zero,
                       COUNT(*) FILTER (WHERE snap_count BETWEEN 1 AND 5) AS bucket_1_5,
                       COUNT(*) FILTER (WHERE snap_count BETWEEN 6 AND 20) AS bucket_6_20,
                       COUNT(*) FILTER (WHERE snap_count BETWEEN 21 AND 50) AS bucket_21_50,
                       COUNT(*) FILTER (WHERE snap_count BETWEEN 51 AND 100) AS bucket_51_100,
                       COUNT(*) FILTER (WHERE snap_count > 100) AS bucket_100_plus,
                       ROUND(AVG(snap_count)::numeric, 1) AS avg_snaps,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY snap_count) AS median_snaps
                FROM outcome_snaps
            """), {"src": src})).first()

            total_outcomes = (await session.execute(text("""
                SELECT COUNT(*) FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.source = :src AND fm.status IN ('open', 'active')
            """), {"src": src})).scalar()

            if sample and sample.total > 0:
                r = sample
                all_sources.append({
                    "source": src,
                    "total_outcomes": total_outcomes or 0,
                    "sampled_outcomes": r.total,
                    "zero_snapshots": r.zero,
                    "1_to_5": r.bucket_1_5,
                    "6_to_20": r.bucket_6_20,
                    "21_to_50": r.bucket_21_50,
                    "51_to_100": r.bucket_51_100,
                    "100_plus": r.bucket_100_plus,
                    "avg_snapshots": float(r.avg_snaps) if r.avg_snaps else 0,
                    "median_snapshots": float(r.median_snaps) if r.median_snaps else 0,
                    "sparse_pct": round(
                        100 * (r.zero + r.bucket_1_5) / max(r.total, 1), 1
                    ),
                })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "method": "200 most-recent markets per source (open/active only)",
        "sources": sorted(all_sources, key=lambda s: s["source"]),
    }

    redis = get_redis()
    redis.setex(SNAPSHOT_DIST_KEY, SNAPSHOT_DIST_TTL, json.dumps(result))
    logger.info(
        "Snapshot distribution computed: %d sources, written to Redis",
        len(all_sources),
    )
    return result
