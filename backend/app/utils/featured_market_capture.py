"""Capture daily featured/top-volume markets from Kalshi and Polymarket.

Neither Kalshi nor Polymarket exposes a "featured" API endpoint,
so we use top-20 by 24h volume as a proxy for front-page prominence.
Results are stored as advisory ground truth for Discover ranking review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FeaturedMarketCapture, FuturesMarket

logger = logging.getLogger(__name__)

TOP_N = 20  # Number of markets to capture per source


async def capture_kalshi_featured(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Capture top Kalshi markets by 24h volume as 'featured' proxy.

    Queries the local DB (populated by poll_kalshi_markets) rather than
    making additional Kalshi API calls.
    """
    now = now or datetime.now(timezone.utc)
    captured_date = now.strftime("%Y-%m-%d")
    source = "kalshi_featured"

    result = await session.execute(
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.external_id,
            FuturesMarket.llm_sport_category,
            FuturesMarket.volume_24h,
            FuturesMarket.image_url,
        )
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.status == "open",
            FuturesMarket.volume_24h.isnot(None),
            FuturesMarket.volume_24h > 0,
        )
        .order_by(FuturesMarket.volume_24h.desc())
        .limit(TOP_N)
    )
    markets = result.all()

    stats = {"source": source, "captured": 0, "skipped": 0, "date": captured_date}

    for rank, (market_id, name, ext_id, category, volume, url) in enumerate(
        markets, start=1
    ):
        if not ext_id:
            stats["skipped"] += 1
            continue

        stmt = pg_insert(FeaturedMarketCapture).values(
            source=source,
            captured_date=captured_date,
            market_name=name[:500],
            external_id=ext_id[:200],
            matched_market_id=market_id,
            category=category,
            url=url,
            rank=rank,
            volume_24h=float(volume) if volume else None,
            captured_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_featured_capture_source_date_ext",
            set_={
                "market_name": stmt.excluded.market_name,
                "matched_market_id": stmt.excluded.matched_market_id,
                "rank": stmt.excluded.rank,
                "volume_24h": stmt.excluded.volume_24h,
                "captured_at": stmt.excluded.captured_at,
            },
        )
        await session.execute(stmt)
        stats["captured"] += 1

    return stats


async def capture_polymarket_featured(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Capture top Polymarket markets by 24h volume as 'featured' proxy.

    Queries the local DB (populated by poll_polymarket_markets) rather
    than making additional Polymarket API calls.
    """
    now = now or datetime.now(timezone.utc)
    captured_date = now.strftime("%Y-%m-%d")
    source = "polymarket_featured"

    result = await session.execute(
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.external_id,
            FuturesMarket.llm_sport_category,
            FuturesMarket.volume_24h,
            FuturesMarket.image_url,
        )
        .where(
            FuturesMarket.source == "polymarket",
            FuturesMarket.status == "open",
            FuturesMarket.volume_24h.isnot(None),
            FuturesMarket.volume_24h > 0,
        )
        .order_by(FuturesMarket.volume_24h.desc())
        .limit(TOP_N)
    )
    markets = result.all()

    stats = {"source": source, "captured": 0, "skipped": 0, "date": captured_date}

    for rank, (market_id, name, ext_id, category, volume, url) in enumerate(
        markets, start=1
    ):
        if not ext_id:
            stats["skipped"] += 1
            continue

        stmt = pg_insert(FeaturedMarketCapture).values(
            source=source,
            captured_date=captured_date,
            market_name=name[:500],
            external_id=ext_id[:200],
            matched_market_id=market_id,
            category=category,
            url=url,
            rank=rank,
            volume_24h=float(volume) if volume else None,
            captured_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_featured_capture_source_date_ext",
            set_={
                "market_name": stmt.excluded.market_name,
                "matched_market_id": stmt.excluded.matched_market_id,
                "rank": stmt.excluded.rank,
                "volume_24h": stmt.excluded.volume_24h,
                "captured_at": stmt.excluded.captured_at,
            },
        )
        await session.execute(stmt)
        stats["captured"] += 1

    return stats


async def capture_all_featured(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run both Kalshi and Polymarket featured captures."""
    now = now or datetime.now(timezone.utc)
    kalshi = await capture_kalshi_featured(session, now=now)
    polymarket = await capture_polymarket_featured(session, now=now)
    await session.commit()
    return {
        "status": "ok",
        "date": now.strftime("%Y-%m-%d"),
        "kalshi": kalshi,
        "polymarket": polymarket,
        "total_captured": kalshi["captured"] + polymarket["captured"],
    }


async def get_featured_capture_status(
    session: AsyncSession,
    *,
    days: int = 7,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build status summary for admin endpoint.

    Returns rows per source per day, match rate, and misses.
    """
    from datetime import timedelta

    now = now or datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    # Rows per source per day
    daily_result = await session.execute(
        select(
            FeaturedMarketCapture.source,
            FeaturedMarketCapture.captured_date,
            sa_func.count(FeaturedMarketCapture.id).label("count"),
            sa_func.count(FeaturedMarketCapture.matched_market_id).label(
                "matched_count"
            ),
        )
        .where(FeaturedMarketCapture.captured_date >= cutoff_date)
        .group_by(
            FeaturedMarketCapture.source,
            FeaturedMarketCapture.captured_date,
        )
        .order_by(
            FeaturedMarketCapture.captured_date.desc(),
            FeaturedMarketCapture.source,
        )
    )
    daily_rows = daily_result.all()

    daily_summary = []
    total_captured = 0
    total_matched = 0
    for source, date, count, matched in daily_rows:
        daily_summary.append(
            {
                "source": source,
                "date": date,
                "count": count,
                "matched": matched,
                "match_rate": round(matched / count, 2) if count > 0 else 0,
            }
        )
        total_captured += count
        total_matched += matched

    # Recent misses: featured markets NOT in our top Discover feed
    # (markets they feature that we don't rank highly)
    miss_result = await session.execute(
        select(
            FeaturedMarketCapture.source,
            FeaturedMarketCapture.captured_date,
            FeaturedMarketCapture.market_name,
            FeaturedMarketCapture.external_id,
            FeaturedMarketCapture.category,
            FeaturedMarketCapture.volume_24h,
            FeaturedMarketCapture.rank,
            FeaturedMarketCapture.matched_market_id,
        )
        .where(
            FeaturedMarketCapture.captured_date >= cutoff_date,
            FeaturedMarketCapture.matched_market_id.isnot(None),
        )
        .order_by(
            FeaturedMarketCapture.captured_date.desc(),
            FeaturedMarketCapture.volume_24h.desc().nullslast(),
        )
        .limit(50)
    )
    recent_captures = [
        {
            "source": r.source,
            "date": r.captured_date,
            "name": r.market_name,
            "external_id": r.external_id,
            "category": r.category,
            "volume_24h": float(r.volume_24h) if r.volume_24h else None,
            "rank": r.rank,
            "matched_market_id": r.matched_market_id,
        }
        for r in miss_result.all()
    ]

    return {
        "days": days,
        "total_captured": total_captured,
        "total_matched": total_matched,
        "overall_match_rate": (
            round(total_matched / total_captured, 2) if total_captured > 0 else 0
        ),
        "daily": daily_summary,
        "recent_captures": recent_captures,
    }
