"""
Event taxonomy Celery task — batch computation of event_tags.

Runs every 2 minutes. Re-tags live events (signal tags change in-game),
tags recently completed events (final EI), and scheduled events within 24h.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.models import Event
from app.tasks.base import get_task_session
from app.utils.event_taxonomy import compute_event_tags
from app.utils.highlights import compute_highlight

logger = logging.getLogger(__name__)


async def _update_event_tags_impl(limit: int = 500, backfill: bool = False) -> dict:
    """Compute and persist event_tags for events needing updates.

    Normal mode processes:
    1. Live events — always re-tag (signal tags change as game progresses)
    2. Scheduled events within 24h — timing/importance tags may have been set
    3. Recently completed (last 6h) without tags — final tags including EI

    Backfill mode processes events with empty/null event_tags regardless of
    status, ordered by commence_time DESC.
    """
    now = datetime.now(timezone.utc)
    stats = {
        "live_tagged": 0,
        "scheduled_tagged": 0,
        "completed_tagged": 0,
        "skipped": 0,
        "errors": 0,
    }

    async with get_task_session() as session:
        if backfill:
            # Backfill: any event with empty/null tags
            query = (
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    or_(
                        Event.event_tags.is_(None),
                        Event.event_tags == [],
                    )
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            events = result.scalars().all()
            for i, event in enumerate(events):
                try:
                    _tag_event(event, now)
                    stats["completed_tagged"] += 1
                except Exception as e:
                    logger.warning("Error tagging event %d: %s", event.id, e)
                    stats["errors"] += 1
                if (i + 1) % 100 == 0:
                    await session.flush()
            return stats

        # ── Tier 1: Live events (always re-tag) ──
        live_query = (
            select(Event)
            .options(selectinload(Event.sport))
            .where(Event.status == "live")
            .limit(limit)
        )
        live_result = await session.execute(live_query)
        live_events = live_result.scalars().all()
        for event in live_events:
            try:
                _tag_event(event, now)
                stats["live_tagged"] += 1
            except Exception as e:
                logger.warning("Error tagging live event %d: %s", event.id, e)
                stats["errors"] += 1

        remaining = limit - len(live_events)
        if remaining <= 0:
            return stats

        # ── Tier 2: Scheduled events within 24h ──
        upcoming_cutoff = now + timedelta(hours=24)
        sched_query = (
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.status == "scheduled",
                Event.commence_time <= upcoming_cutoff,
                Event.commence_time >= now - timedelta(hours=1),
            )
            .limit(remaining)
        )
        sched_result = await session.execute(sched_query)
        sched_events = sched_result.scalars().all()
        for event in sched_events:
            try:
                _tag_event(event, now)
                stats["scheduled_tagged"] += 1
            except Exception as e:
                logger.warning("Error tagging scheduled event %d: %s", event.id, e)
                stats["errors"] += 1

        remaining -= len(sched_events)
        if remaining <= 0:
            return stats

        # ── Tier 3: Recently completed without tags (last 6h) ──
        recent_cutoff = now - timedelta(hours=6)
        completed_query = (
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.commence_time >= recent_cutoff,
                or_(
                    Event.event_tags.is_(None),
                    Event.event_tags == [],
                ),
            )
            .limit(remaining)
        )
        completed_result = await session.execute(completed_query)
        completed_events = completed_result.scalars().all()
        for event in completed_events:
            try:
                _tag_event(event, now)
                stats["completed_tagged"] += 1
            except Exception as e:
                logger.warning("Error tagging completed event %d: %s", event.id, e)
                stats["errors"] += 1

    return stats


def _tag_event(event: Event, now: datetime) -> None:
    """Compute tags for a single event and set event.event_tags."""
    sport_key = event.sport.key if event.sport else ""

    # Derive importance (same logic as feed.py _score_events)
    importance = event.llm_importance
    if not importance or importance == "unknown":
        if "preseason" in sport_key:
            importance = "exhibition"

    # Compute highlight for signal flags — uses opening odds already on the model
    opening_home_prob = float(event.opening_home_probability) if event.opening_home_probability else None
    opening_away_prob = float(event.opening_away_probability) if event.opening_away_probability else None

    highlight_result = compute_highlight(
        status=event.status,
        commence_time=event.commence_time,
        sport_key=sport_key,
        current_home_prob=opening_home_prob,
        current_away_prob=opening_away_prob,
        opening_home_prob=opening_home_prob,
        opening_away_prob=opening_away_prob,
        opening_favorite=event.opening_favorite,
        now=now,
        home_team_name=event.home_team_name,
        away_team_name=event.away_team_name,
        importance=importance,
        end_time=event.statpal_end_time,
    )

    tags = compute_event_tags(
        sport_key=sport_key,
        status=event.status,
        commence_time=event.commence_time,
        llm_importance=importance,
        llm_gender=event.llm_gender,
        llm_level=event.llm_level,
        llm_league=event.llm_league,
        raw_ei=float(event.raw_ei) if event.raw_ei else None,
        broadcast_info=event.broadcast_info,
        highlight_result=highlight_result,
    )

    event.event_tags = tags
