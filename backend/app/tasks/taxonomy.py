"""
Taxonomy tag computation Celery task.

Computes deterministic event_tags and market_tags for events and futures markets.
Runs every 2 minutes to keep tags fresh for live events and new futures.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, or_, update

from app.tasks.base import get_task_session
from app.models.models import Event, FuturesMarket
from app.utils.aggregation import compute_aggregate_probability
from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
from app.utils.highlights import compute_highlight

logger = logging.getLogger(__name__)


async def _update_event_tags_impl(limit: int = 500) -> dict:
    """Compute and persist event_tags for events that need tagging.

    Processes:
    1. Live events (always refresh — signals change in real-time)
    2. Events updated in the last 30 min (catch newly completed games)
    3. Events with null/empty event_tags (backfill)
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=30)

    async with get_task_session() as session:
        # Query events needing tag updates
        stmt = (
            select(Event)
            .where(
                or_(
                    # Live events — always refresh
                    Event.status == "live",
                    # Recently updated — catch completions
                    and_(
                        Event.status.in_(["completed", "closed", "scheduled"]),
                        Event.commence_time >= cutoff - timedelta(hours=6),
                    ),
                    # Backfill: missing tags
                    Event.event_tags == None,  # noqa: E711
                    Event.event_tags == [],
                )
            )
            .order_by(
                # Prioritize live, then recent, then backfill
                Event.status.desc(),
                Event.commence_time.desc(),
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        tagged = 0
        errors = 0

        for event in events:
            try:
                tags = _tag_event(event)
                event.event_tags = tags
                tagged += 1
            except Exception:
                logger.exception("Failed to tag event %s", event.id)
                errors += 1

        if tagged > 0:
            await session.commit()

        # --- Futures market tags ---
        futures_tagged = await _update_market_tags(session, limit=limit)

        return {
            "events_tagged": tagged,
            "events_errors": errors,
            "futures_tagged": futures_tagged,
        }


def _tag_event(event: Event) -> list[str]:
    """Compute tags for a single event using current aggregate probability."""
    # Get current aggregate probability (not just opening odds)
    current_home_prob = compute_aggregate_probability(event)
    opening_home_prob = (
        float(event.opening_home_probability)
        if event.opening_home_probability is not None
        else None
    )

    # Compute current away probability
    current_away_prob = (1.0 - current_home_prob) if current_home_prob is not None else None
    opening_away_prob = (1.0 - opening_home_prob) if opening_home_prob is not None else None

    # Compute highlight result (provides signal flags like upset, close, line_moving)
    highlight_result = None
    if opening_home_prob is not None and current_home_prob is not None:
        highlight_result = compute_highlight(
            sport_key=event.sport_key,
            status=event.status,
            commence_time=event.commence_time,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            current_home_prob=current_home_prob,
            current_away_prob=current_away_prob,
            home_score=event.home_score,
            away_score=event.away_score,
            llm_importance=getattr(event, "llm_importance", None),
        )

    # Get raw EI score
    raw_ei = float(event.raw_ei) if event.raw_ei is not None else None

    return compute_event_tags(
        sport_key=event.sport_key,
        status=event.status,
        commence_time=event.commence_time,
        llm_importance=getattr(event, "llm_importance", None),
        llm_gender=getattr(event, "llm_gender", None),
        llm_level=getattr(event, "llm_level", None),
        llm_league=getattr(event, "llm_league", None),
        raw_ei=raw_ei,
        broadcast_info=getattr(event, "broadcast_info", None),
        highlight_result=highlight_result,
    )


async def _update_market_tags(session, limit: int = 500) -> int:
    """Compute and persist market_tags for futures markets.

    Processes open markets with null/empty market_tags, plus recently updated.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=30)

    stmt = (
        select(FuturesMarket)
        .where(
            or_(
                # Backfill: missing tags
                FuturesMarket.market_tags == None,  # noqa: E711
                FuturesMarket.market_tags == [],
                # Recently updated open markets
                and_(
                    FuturesMarket.status == "open",
                    FuturesMarket.updated_at >= cutoff,
                ),
            )
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    markets = result.scalars().all()

    tagged = 0
    for market in markets:
        try:
            tags = compute_market_tags(
                llm_sport_category=market.llm_sport_category,
                llm_league=getattr(market, "llm_league", None),
                llm_gender=getattr(market, "llm_gender", None),
                llm_level=getattr(market, "llm_level", None),
                market_tier=market.market_tier,
                category=market.category,
                status=market.status,
                source=market.source,
            )
            market.market_tags = tags
            tagged += 1
        except Exception:
            logger.exception("Failed to tag market %s", market.id)

    if tagged > 0:
        await session.commit()

    return tagged
