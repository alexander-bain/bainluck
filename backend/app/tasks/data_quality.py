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
from sqlalchemy import func, select, case, and_, or_

from app.models import FuturesMarket, FuturesOutcome
from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

# Thresholds for alerting
_UNCLASSIFIED_RATE_WARN = 0.15   # >15% tier-5 = context warning (ceiling-lag)
_UNCLASSIFIED_RATE_CRIT = 0.30   # >30% tier-5 = critical ONLY if not surge-explained
_UNLINKED_RATE_WARN = 0.40       # >40% outcomes without team_id = warning

# The HONEST "unclassified" signal: the category classifier genuinely failed
# (llm_sport_category IS NULL). market_tier=5 is the VALID commodity bottom tier —
# a legit ingest surge of individual match markets (Polymarket soccer/baseball/
# tennis) correctly lands there, so alarming on tier-5 alone cries wolf. (r255:
# a 26.5K commodity surge tripped a false CRITICAL while the category classifier
# was healthy — 4 nulls — and tiering was actively promoting 1.2K markets to 1-4.)
_CATEGORY_NULL_RATE_WARN = 0.15
_CATEGORY_NULL_RATE_CRIT = 0.30
# An ingest surge explains a tier-5 spike as ceiling-lag, not a stall.
_INGEST_SURGE_ABS = 5000         # ≥ this many new markets in 24h == a surge
_INGEST_SURGE_RATE = 0.40        # or new markets are ≥40% of the 24h sports window

_NON_SPORT_CATEGORIES = {
    "politics", "crypto", "economics", "entertainment", "tech",
    "weather", "geopolitics", "culture", "health", "legal", "other",
}


def classify_classification_health(
    *,
    total_markets: int,
    tier_5_rate: float,
    tier_5_count: int,
    category_null_rate: float,
    category_null_count: int,
    tiering_active: bool,
    tiered_count: int,
    is_ingest_surge: bool,
) -> dict | None:
    """Pure alert-severity decision for the classification health check.

    Distinguishes a genuine STALL (paged CRITICAL) from benign ceiling-lag
    (INFO). Returns ``{"severity", "message"}`` or None when nothing is wrong.

    * CRITICAL only when the category classifier genuinely stalled (no
      llm_sport_category), OR tiering stalled (tier-5 flood with zero promotions
      AND no ingest surge to explain it).
    * A tier-5 spike explained by an ingest surge / bounded tiering, while the
      category classifier is healthy, is INFO — never a page. (r255's false
      CRITICAL was exactly this: a 26.5K commodity match-market surge.)
    """
    if total_markets < 10:
        return None
    if category_null_rate > _CATEGORY_NULL_RATE_CRIT:
        return {
            "severity": "critical",
            "message": (
                f"CRITICAL: category classifier stalled — {category_null_rate:.0%} "
                f"of markets have no llm_sport_category "
                f"({category_null_count}/{total_markets}) in last 24h"
            ),
        }
    if tier_5_rate > _UNCLASSIFIED_RATE_CRIT and not tiering_active and not is_ingest_surge:
        return {
            "severity": "critical",
            "message": (
                f"CRITICAL: tiering stalled — {tier_5_rate:.0%} tier-5 "
                f"({tier_5_count}/{total_markets}) with 0 promotions and no ingest "
                f"surge in last 24h"
            ),
        }
    if category_null_rate > _CATEGORY_NULL_RATE_WARN:
        return {
            "severity": "warning",
            "message": (
                f"WARNING: {category_null_rate:.0%} of markets have no "
                f"llm_sport_category ({category_null_count}/{total_markets}) in last 24h"
            ),
        }
    if tier_5_rate > _UNCLASSIFIED_RATE_WARN:
        reason = "ingest surge" if is_ingest_surge else "bounded tiering"
        return {
            "severity": "info",
            "message": (
                f"INFO: tier-5 elevated ({tier_5_rate:.0%}, {tier_5_count}/"
                f"{total_markets}) — ceiling-lag ({reason}); category healthy "
                f"({category_null_rate:.0%} null), {tiered_count} promoted to 1-4"
            ),
        }
    return None


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
        # ── Check 1: Classification distribution (last 24h sports markets) ──
        tier_dist = await session.execute(
            select(
                FuturesMarket.market_tier,
                func.count(FuturesMarket.id),
            )
            .where(
                FuturesMarket.updated_at >= since,
                or_(
                    FuturesMarket.llm_sport_category.is_(None),
                    FuturesMarket.llm_sport_category.notin_(_NON_SPORT_CATEGORIES),
                ),
            )
            .group_by(FuturesMarket.market_tier)
        )
        tier_counts = {str(row[0]): row[1] for row in tier_dist.all()}
        total_markets = sum(tier_counts.values())

        tier_5_count = tier_counts.get("5", 0) + tier_counts.get("None", 0)
        tier_5_rate = tier_5_count / total_markets if total_markets > 0 else 0
        # Tiering-active signal: markets promoted to a real quality tier (1-4).
        tiered_count = sum(tier_counts.get(str(t), 0) for t in (1, 2, 3, 4))

        # The HONEST unclassified signal: the category classifier failed (no
        # llm_sport_category). Same sports scope + 24h window as the tier query.
        category_null_count = (
            await session.execute(
                select(func.count(FuturesMarket.id)).where(
                    FuturesMarket.updated_at >= since,
                    FuturesMarket.llm_sport_category.is_(None),
                )
            )
        ).scalar() or 0
        category_null_rate = (
            category_null_count / total_markets if total_markets > 0 else 0
        )

        # Ingest surge (sports scope, 24h): a flood of newly-created match markets
        # explains a tier-5 spike as ceiling-lag, not a stall.
        new_markets_24h = (
            await session.execute(
                select(func.count(FuturesMarket.id)).where(
                    FuturesMarket.created_at >= since,
                    or_(
                        FuturesMarket.llm_sport_category.is_(None),
                        FuturesMarket.llm_sport_category.notin_(_NON_SPORT_CATEGORIES),
                    ),
                )
            )
        ).scalar() or 0
        is_ingest_surge = new_markets_24h >= _INGEST_SURGE_ABS or (
            total_markets > 0 and new_markets_24h / total_markets >= _INGEST_SURGE_RATE
        )
        tiering_active = tiered_count > 0

        report["checks"]["classification"] = {
            "total_markets_24h": total_markets,
            "tier_distribution": tier_counts,
            # Retained for dashboard continuity, but tier-5 is NOT "unclassified".
            "tier5_count": tier_5_count,
            "tier5_rate": round(tier_5_rate, 3),
            # The honest classifier-health signal.
            "category_null_count": category_null_count,
            "category_null_rate": round(category_null_rate, 3),
            "tiered_count_24h": tiered_count,
            "new_markets_24h": new_markets_24h,
            "ingest_surge": is_ingest_surge,
            "scope": "sports_only",
        }

        # ── Alerting: distinguish a real STALL (paged) from ceiling-lag (info) ──
        verdict = classify_classification_health(
            total_markets=total_markets,
            tier_5_rate=tier_5_rate,
            tier_5_count=tier_5_count,
            category_null_rate=category_null_rate,
            category_null_count=category_null_count,
            tiering_active=tiering_active,
            tiered_count=tiered_count,
            is_ingest_surge=is_ingest_surge,
        )
        if verdict:
            report["alerts"].append(verdict["message"])
            if verdict["severity"] == "critical":
                sentry_sdk.capture_message(
                    f"[BainLuck Data Quality] {verdict['message']}", level="error"
                )
                logger.error(verdict["message"])
            elif verdict["severity"] == "warning":
                logger.warning(verdict["message"])
            else:
                logger.info(verdict["message"])

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
