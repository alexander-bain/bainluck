"""
Data quality monitoring for market classification and matching.

Periodic task that checks classification health, stores a report in Redis,
and alerts via Sentry when thresholds are breached.

Checks:
1. Unclassified markets (tier=5 or category="other") created in last 24h
2. Markets with no team links (outcomes with NULL team_id)
3. Prediction market matching coverage
4. Overall classification distribution
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import sentry_sdk
from sqlalchemy import func, select, case, and_

from app.models import FuturesMarket, FuturesOutcome
from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

# Thresholds for alerting
_UNCLASSIFIED_RATE_WARN = 0.15   # >15% unclassified = warning
_UNCLASSIFIED_RATE_CRIT = 0.30   # >30% unclassified = critical
_UNLINKED_RATE_WARN = 0.40       # >40% outcomes without team_id = warning

_NON_SPORT_CATEGORIES = {
    "politics", "crypto", "economics", "entertainment", "tech",
    "weather", "geopolitics", "culture", "health", "legal", "other",
}


async def _check_data_quality() -> dict:
    """Run classification and matching health checks.

    Returns a report dict and stores it in Redis for the admin dashboard.
    Sends Sentry alerts for critical issues.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    report = {
        "timestamp": now.isoformat(),
        "period": "last_24h",
        "checks": {},
        "alerts": [],
    }

    async with get_task_session() as session:
        # ── Check 1: Classification distribution (last 24h markets) ──
        tier_dist = await session.execute(
            select(
                FuturesMarket.market_tier,
                func.count(FuturesMarket.id),
            )
            .where(FuturesMarket.updated_at >= since)
            .group_by(FuturesMarket.market_tier)
        )
        tier_counts = {str(row[0]): row[1] for row in tier_dist.all()}
        total_markets = sum(tier_counts.values())

        tier_5_count = tier_counts.get("5", 0) + tier_counts.get("None", 0)
        tier_5_rate = tier_5_count / total_markets if total_markets > 0 else 0

        report["checks"]["classification"] = {
            "total_markets_24h": total_markets,
            "tier_distribution": tier_counts,
            "unclassified_count": tier_5_count,
            "unclassified_rate": round(tier_5_rate, 3),
        }

        if tier_5_rate > _UNCLASSIFIED_RATE_CRIT and total_markets >= 10:
            alert = (
                f"CRITICAL: {tier_5_rate:.0%} of markets unclassified "
                f"({tier_5_count}/{total_markets}) in last 24h"
            )
            report["alerts"].append(alert)
            sentry_sdk.capture_message(
                f"[BainLuck Data Quality] {alert}",
                level="error",
            )
            logger.error(alert)
        elif tier_5_rate > _UNCLASSIFIED_RATE_WARN and total_markets >= 10:
            alert = (
                f"WARNING: {tier_5_rate:.0%} of markets unclassified "
                f"({tier_5_count}/{total_markets}) in last 24h"
            )
            report["alerts"].append(alert)
            logger.warning(alert)

        # ── Check 2: Sample unclassified market names (for diagnosis) ──
        unclassified_sample = await session.execute(
            select(FuturesMarket.name, FuturesMarket.source)
            .where(
                and_(
                    FuturesMarket.updated_at >= since,
                    FuturesMarket.market_tier == 5,
                    FuturesMarket.status != "resolved",
                )
            )
            .order_by(func.random())
            .limit(20)
        )
        samples = [
            {"name": row[0], "source": row[1]}
            for row in unclassified_sample.all()
        ]
        report["checks"]["unclassified_samples"] = samples

        # ── Check 3: Team linking coverage (sports markets only) ──
        # Non-sport markets (politics, weather, etc.) can't have team links,
        # so measuring them inflates the "unlinked" rate meaninglessly.
        linking_stats = await session.execute(
            select(
                func.count(FuturesOutcome.id).label("total"),
                func.count(FuturesOutcome.team_id).label("linked"),
            )
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .where(
                FuturesMarket.status != "resolved",
                FuturesMarket.llm_sport_category.isnot(None),
                FuturesMarket.llm_sport_category.notin_(_NON_SPORT_CATEGORIES),
            )
        )
        link_row = linking_stats.one()
        total_outcomes = link_row[0]
        linked_outcomes = link_row[1]
        unlinked_rate = (
            (total_outcomes - linked_outcomes) / total_outcomes
            if total_outcomes > 0 else 0
        )

        # Also count non-sport markets for context
        non_sport_count = await session.execute(
            select(func.count(FuturesMarket.id))
            .where(
                FuturesMarket.status != "resolved",
                FuturesMarket.llm_sport_category.in_(_NON_SPORT_CATEGORIES),
            )
        )

        report["checks"]["team_linking"] = {
            "total_outcomes": total_outcomes,
            "linked_outcomes": linked_outcomes,
            "unlinked_rate": round(unlinked_rate, 3),
            "scope": "sports_only",
            "non_sport_markets": non_sport_count.scalar() or 0,
        }

        if unlinked_rate > _UNLINKED_RATE_WARN and total_outcomes >= 50:
            alert = (
                f"WARNING: {unlinked_rate:.0%} of sports outcomes missing team_id "
                f"({total_outcomes - linked_outcomes}/{total_outcomes})"
            )
            report["alerts"].append(alert)
            logger.warning(alert)

        # ── Check 4: Source coverage ──
        source_dist = await session.execute(
            select(
                FuturesMarket.source,
                func.count(FuturesMarket.id),
            )
            .where(FuturesMarket.status != "resolved")
            .group_by(FuturesMarket.source)
        )
        report["checks"]["source_distribution"] = {
            row[0]: row[1] for row in source_dist.all()
        }

    # ── Store in Redis ──
    try:
        from app.tasks.redis_state import get_redis_client
        r = get_redis_client()
        r.setex(
            "bainluck:data_quality:latest",
            86400,  # 24h TTL
            json.dumps(report),
        )
        # Also store in a list for history (keep last 30 days)
        date_key = now.strftime("%Y-%m-%d")
        r.setex(
            f"bainluck:data_quality:{date_key}",
            86400 * 30,
            json.dumps(report),
        )
    except Exception as e:
        logger.warning(f"Redis cache error for data quality report: {e}")

    status = "critical" if any("CRITICAL" in a for a in report["alerts"]) else (
        "warning" if report["alerts"] else "healthy"
    )
    report["status"] = status

    logger.info(
        "Data quality check complete: status=%s, markets=%d, unclassified=%d (%.1f%%), alerts=%d",
        status, total_markets, tier_5_count, tier_5_rate * 100, len(report["alerts"]),
    )

    return report
