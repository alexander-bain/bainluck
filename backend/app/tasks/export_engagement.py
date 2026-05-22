"""Nightly export of Discover engagement data for ranking review.

Queries DiscoverInteraction from the last 24h, joins with FuturesMarket
for category/score context, and aggregates per-market and per-category
engagement rates. Stores a JSON summary in Redis for the admin review
endpoint to read without running heavy queries on every request.

This is REPORTING only — it never auto-tunes production ranking weights.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

REDIS_KEY = "engagement_review:latest"
REDIS_TTL_SECONDS = 48 * 3600  # 48 hours


def _score_bucket_label(score: int | None) -> str:
    """Map a numeric score to a 20-point bucket label."""
    if score is None:
        return "unknown"
    try:
        value = int(score)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 100:
        return "80-100"
    if value >= 80:
        return "80-100"
    if value >= 60:
        return "60-80"
    if value >= 40:
        return "40-60"
    if value >= 20:
        return "20-40"
    return "0-20"


async def _export_engagement_impl() -> dict:
    """Build and cache the nightly engagement review summary."""
    from sqlalchemy import select, func, case, and_

    from app.models.models import DiscoverInteraction, FuturesMarket

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    async with get_task_session() as session:
        # ------------------------------------------------------------------
        # Step 1: Per-market aggregation from DiscoverInteraction
        # ------------------------------------------------------------------
        market_agg_result = await session.execute(
            select(
                DiscoverInteraction.item_type,
                DiscoverInteraction.item_id,
                func.max(DiscoverInteraction.item_name).label("item_name"),
                func.max(DiscoverInteraction.category).label("category"),
                func.max(DiscoverInteraction.score).label("score"),
                func.count(
                    case(
                        (DiscoverInteraction.action == "impression", DiscoverInteraction.id),
                        else_=None,
                    )
                ).label("impression_count"),
                func.count(
                    case(
                        (DiscoverInteraction.action.in_(("detail_click", "open")), DiscoverInteraction.id),
                        else_=None,
                    )
                ).label("open_count"),
                func.count(
                    case(
                        (DiscoverInteraction.action == "dismiss", DiscoverInteraction.id),
                        else_=None,
                    )
                ).label("dismiss_count"),
                func.count(
                    case(
                        (DiscoverInteraction.action.in_(("like", "unlike")), DiscoverInteraction.id),
                        else_=None,
                    )
                ).label("like_count"),
                func.count(
                    case(
                        (DiscoverInteraction.action == "share", DiscoverInteraction.id),
                        else_=None,
                    )
                ).label("share_count"),
            )
            .where(DiscoverInteraction.created_at >= cutoff)
            .group_by(DiscoverInteraction.item_type, DiscoverInteraction.item_id)
        )

        per_market: list[dict] = []
        for row in market_agg_result.all():
            impressions = int(row.impression_count or 0)
            opens = int(row.open_count or 0)
            likes = int(row.like_count or 0)
            shares = int(row.share_count or 0)
            dismisses = int(row.dismiss_count or 0)
            engagement_rate = (
                (opens + likes + shares) / impressions if impressions > 0 else 0.0
            )
            per_market.append({
                "item_type": row.item_type or "unknown",
                "item_id": str(row.item_id),
                "item_name": row.item_name,
                "category": row.category or "other",
                "score": int(row.score) if row.score is not None else None,
                "impression_count": impressions,
                "open_count": opens,
                "dismiss_count": dismisses,
                "like_count": likes,
                "share_count": shares,
                "engagement_rate": round(engagement_rate, 4),
            })

        # ------------------------------------------------------------------
        # Step 2: Per-category aggregation
        # ------------------------------------------------------------------
        cat_buckets: dict[str, dict] = {}
        for m in per_market:
            cat = m["category"]
            bucket = cat_buckets.setdefault(cat, {
                "category": cat,
                "total_impressions": 0,
                "total_opens": 0,
                "total_likes": 0,
                "total_shares": 0,
                "total_dismisses": 0,
                "market_count": 0,
                "score_sum": 0,
                "score_count": 0,
                "engagement_rates": [],
            })
            bucket["total_impressions"] += m["impression_count"]
            bucket["total_opens"] += m["open_count"]
            bucket["total_likes"] += m["like_count"]
            bucket["total_shares"] += m["share_count"]
            bucket["total_dismisses"] += m["dismiss_count"]
            bucket["market_count"] += 1
            if m["score"] is not None:
                bucket["score_sum"] += m["score"]
                bucket["score_count"] += 1
            if m["impression_count"] >= 3:  # skip very low-impression items
                bucket["engagement_rates"].append(m["engagement_rate"])

        by_category = []
        for cat, bucket in cat_buckets.items():
            avg_score = (
                round(bucket["score_sum"] / bucket["score_count"], 1)
                if bucket["score_count"] > 0
                else None
            )
            rates = bucket["engagement_rates"]
            avg_engagement_rate = (
                round(sum(rates) / len(rates), 4) if rates else 0.0
            )

            # Top and bottom markets by engagement rate for this category
            cat_markets = [
                m for m in per_market
                if m["category"] == cat and m["impression_count"] >= 3
            ]
            cat_markets_sorted = sorted(
                cat_markets, key=lambda x: x["engagement_rate"], reverse=True
            )
            top_markets = [
                {
                    "item_id": m["item_id"],
                    "item_name": m["item_name"],
                    "score": m["score"],
                    "engagement_rate": m["engagement_rate"],
                    "impressions": m["impression_count"],
                }
                for m in cat_markets_sorted[:5]
            ]
            bottom_markets = [
                {
                    "item_id": m["item_id"],
                    "item_name": m["item_name"],
                    "score": m["score"],
                    "engagement_rate": m["engagement_rate"],
                    "impressions": m["impression_count"],
                }
                for m in cat_markets_sorted[-5:]
            ] if len(cat_markets_sorted) > 5 else []

            by_category.append({
                "category": cat,
                "avg_score": avg_score,
                "avg_engagement_rate": avg_engagement_rate,
                "market_count": bucket["market_count"],
                "total_impressions": bucket["total_impressions"],
                "top_markets": top_markets,
                "bottom_markets": bottom_markets,
            })

        by_category.sort(key=lambda x: x["total_impressions"], reverse=True)

        # ------------------------------------------------------------------
        # Step 3: Score-bucket aggregation
        # ------------------------------------------------------------------
        score_agg: dict[str, dict] = {}
        for m in per_market:
            label = _score_bucket_label(m["score"])
            bucket = score_agg.setdefault(label, {
                "score_range": label,
                "market_count": 0,
                "total_impressions": 0,
                "total_opens": 0,
                "total_shares": 0,
                "total_likes": 0,
                "total_dismisses": 0,
            })
            bucket["market_count"] += 1
            bucket["total_impressions"] += m["impression_count"]
            bucket["total_opens"] += m["open_count"]
            bucket["total_shares"] += m["share_count"]
            bucket["total_likes"] += m["like_count"]
            bucket["total_dismisses"] += m["dismiss_count"]

        score_buckets = []
        for label, bucket in score_agg.items():
            imps = bucket["total_impressions"]
            engagement_rate = (
                (bucket["total_opens"] + bucket["total_likes"] + bucket["total_shares"])
                / imps
                if imps > 0
                else 0.0
            )
            score_buckets.append({
                **bucket,
                "avg_engagement_rate": round(engagement_rate, 4),
            })
        # Sort by score range
        order = {"0-20": 0, "20-40": 1, "40-60": 2, "60-80": 3, "80-100": 4, "unknown": 5}
        score_buckets.sort(key=lambda x: order.get(x["score_range"], 99))

        # ------------------------------------------------------------------
        # Step 4: Opportunities — under-ranked and over-ranked
        # ------------------------------------------------------------------
        # Only consider markets with enough impressions
        eligible = [m for m in per_market if m["impression_count"] >= 5]

        # Under-ranked: high engagement, low score
        under_ranked = sorted(
            [
                m for m in eligible
                if m["engagement_rate"] >= 0.15
                and m["score"] is not None
                and m["score"] < 40
            ],
            key=lambda x: x["engagement_rate"],
            reverse=True,
        )[:10]

        # Over-ranked: low engagement, high score
        over_ranked = sorted(
            [
                m for m in eligible
                if m["engagement_rate"] <= 0.03
                and m["score"] is not None
                and m["score"] >= 60
            ],
            key=lambda x: x["score"],
            reverse=True,
        )[:10]

        opportunities = {
            "under_ranked": [
                {
                    "item_id": m["item_id"],
                    "item_name": m["item_name"],
                    "category": m["category"],
                    "score": m["score"],
                    "engagement_rate": m["engagement_rate"],
                    "impressions": m["impression_count"],
                    "verdict": "under-ranked",
                }
                for m in under_ranked
            ],
            "over_ranked": [
                {
                    "item_id": m["item_id"],
                    "item_name": m["item_name"],
                    "category": m["category"],
                    "score": m["score"],
                    "engagement_rate": m["engagement_rate"],
                    "impressions": m["impression_count"],
                    "verdict": "over-ranked",
                }
                for m in over_ranked
            ],
        }

        # ------------------------------------------------------------------
        # Step 5: Store in Redis
        # ------------------------------------------------------------------
        summary = {
            "generated_at": now.isoformat(),
            "window_hours": 24,
            "total_markets_with_interactions": len(per_market),
            "by_category": by_category,
            "score_buckets": score_buckets,
            "opportunities": opportunities,
        }

        try:
            from app.tasks.redis_state import get_redis_client

            r = get_redis_client()
            r.set(REDIS_KEY, json.dumps(summary), ex=REDIS_TTL_SECONDS)
            logger.info(
                "Engagement review exported: %d markets, %d categories",
                len(per_market),
                len(by_category),
            )
        except Exception as exc:
            logger.warning("Failed to write engagement review to Redis: %s", exc)
            summary["redis_error"] = str(exc)[:200]

        return {
            "status": "ok",
            "markets_analyzed": len(per_market),
            "categories": len(by_category),
            "under_ranked": len(under_ranked),
            "over_ranked": len(over_ranked),
        }
