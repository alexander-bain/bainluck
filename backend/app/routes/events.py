"""Events API endpoints."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, not_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, OddsSnapshot, Sport
from app.services import get_db, OddsAPIService, fetch_current_odds
from app.utils import moneyline_to_probability, project_scores, calculate_gei

router = APIRouter()

# Excluded sport prefixes (no soccer!)
EXCLUDED_SPORT_PREFIXES = ["soccer_"]


@router.get("")
async def list_events(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    status: Optional[str] = Query(None, description="Filter by status"),
    days: int = Query(7, description="Number of days ahead to show"),
    db: AsyncSession = Depends(get_db),
):
    """
    List upcoming and live events.

    Returns events with their current win probabilities.
    Memory-optimized: only fetches latest odds snapshot per event.
    """
    # Build query - only load sport, NOT all odds_snapshots (too much memory)
    query = select(Event).options(
        selectinload(Event.sport),
    )

    conditions = []

    if sport:
        conditions.append(Event.sport.has(Sport.key == sport))

    if status:
        conditions.append(Event.status == status)
    else:
        # Default: show scheduled and live
        conditions.append(Event.status.in_(["scheduled", "live"]))

    # Date range - but always include live games regardless of start time
    now = datetime.utcnow()
    end_date = now + timedelta(days=days)

    # Show events that either:
    # 1. Are live (regardless of when they started), OR
    # 2. Are scheduled and start within the date range
    conditions.append(
        or_(
            Event.status == "live",
            and_(
                Event.commence_time >= now,
                Event.commence_time <= end_date
            )
        )
    )

    # Exclude soccer (and any other excluded sports)
    for prefix in EXCLUDED_SPORT_PREFIXES:
        conditions.append(not_(Event.sport.has(Sport.key.startswith(prefix))))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Event.commence_time)

    result = await db.execute(query)
    events = result.scalars().all()

    # Get only the latest odds snapshot for each event (memory efficient)
    event_ids = [e.id for e in events]
    latest_odds_map = {}

    if event_ids:
        # Subquery to get the max captured_at per event
        latest_time_subq = (
            select(
                OddsSnapshot.event_id,
                func.max(OddsSnapshot.captured_at).label("max_time")
            )
            .where(OddsSnapshot.event_id.in_(event_ids))
            .group_by(OddsSnapshot.event_id)
            .subquery()
        )

        # Get the actual snapshots matching the max times
        latest_odds_query = (
            select(OddsSnapshot)
            .join(
                latest_time_subq,
                and_(
                    OddsSnapshot.event_id == latest_time_subq.c.event_id,
                    OddsSnapshot.captured_at == latest_time_subq.c.max_time
                )
            )
        )

        latest_odds_result = await db.execute(latest_odds_query)
        for snap in latest_odds_result.scalars().all():
            latest_odds_map[snap.event_id] = snap

    # Format response with latest odds
    return {
        "events": [
            _format_event_with_latest_odds(e, latest_odds_map.get(e.id))
            for e in events
        ],
        "count": len(events),
    }


@router.get("/live")
async def list_live_events(db: AsyncSession = Depends(get_db)):
    """List currently live events."""
    result = await db.execute(
        select(Event)
        .where(Event.status == "live")
        .order_by(Event.commence_time)
    )
    events = result.scalars().all()
    
    return {
        "events": [_format_event(e) for e in events],
        "count": len(events),
    }


@router.get("/live-odds/{sport_key}")
async def get_live_odds(sport_key: str):
    """
    Fetch live odds directly from API (not from database).
    
    Useful for real-time updates without waiting for the
    polling job. Use sparingly to conserve API quota.
    """
    try:
        snapshots = await fetch_current_odds(sport_key)
        
        # Group by event
        events_map = {}
        for snap in snapshots:
            if snap.event_id not in events_map:
                events_map[snap.event_id] = {
                    "event_id": snap.event_id,
                    "home_team": snap.home_team,
                    "away_team": snap.away_team,
                    "commence_time": snap.commence_time.isoformat(),
                    "bookmakers": [],
                }
            
            # Calculate probability
            home_prob = None
            away_prob = None
            if snap.home_moneyline and snap.away_moneyline:
                home_prob, away_prob = moneyline_to_probability(
                    snap.home_moneyline, snap.away_moneyline
                )
            
            events_map[snap.event_id]["bookmakers"].append({
                "key": snap.bookmaker,
                "home_moneyline": snap.home_moneyline,
                "away_moneyline": snap.away_moneyline,
                "home_probability": round(home_prob, 4) if home_prob else None,
                "away_probability": round(away_prob, 4) if away_prob else None,
                "spread": snap.home_spread,
                "over_under": float(snap.over_under) if snap.over_under else None,
            })
        
        return {
            "sport": sport_key,
            "events": list(events_map.values()),
            "count": len(events_map),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch odds: {str(e)}"
        )


@router.get("/{event_id}")
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Get event details with current odds."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.odds_snapshots), selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Get latest odds snapshot
    latest_odds = None
    if event.odds_snapshots:
        latest_odds = max(
            event.odds_snapshots, 
            key=lambda x: x.captured_at
        )
    
    response = _format_event(event)
    
    if latest_odds:
        response["current_odds"] = {
            "bookmaker": latest_odds.bookmaker,
            "captured_at": latest_odds.captured_at.isoformat(),
            "home_moneyline": latest_odds.home_moneyline,
            "away_moneyline": latest_odds.away_moneyline,
            "home_probability": float(latest_odds.home_win_probability) 
                if latest_odds.home_win_probability else None,
            "away_probability": float(latest_odds.away_win_probability)
                if latest_odds.away_win_probability else None,
            "spread": float(latest_odds.home_spread) 
                if latest_odds.home_spread else None,
            "over_under": float(latest_odds.over_under)
                if latest_odds.over_under else None,
            "projected_home_score": float(latest_odds.projected_home_score)
                if latest_odds.projected_home_score else None,
            "projected_away_score": float(latest_odds.projected_away_score)
                if latest_odds.projected_away_score else None,
        }
    
    return response


@router.get("/{event_id}/history")
async def get_event_odds_history(
    event_id: int,
    hours: int = Query(24, description="Hours of history to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get odds history for trending chart.
    
    Returns probability snapshots over time for visualization.
    """
    # Verify event exists
    event_result = await db.execute(
        select(Event).where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Get snapshots within time range
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    result = await db.execute(
        select(OddsSnapshot)
        .where(
            and_(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.captured_at >= cutoff,
            )
        )
        .order_by(OddsSnapshot.captured_at)
    )
    snapshots = result.scalars().all()
    
    # Format for charting
    # Include valid_until for drawing flat lines between data points
    history = []
    for snap in snapshots:
        point = {
            "timestamp": snap.captured_at.isoformat(),
            "home_probability": float(snap.home_win_probability)
                if snap.home_win_probability else None,
            "away_probability": float(snap.away_win_probability)
                if snap.away_win_probability else None,
            "over_under": float(snap.over_under)
                if snap.over_under else None,
            "projected_home_score": float(snap.projected_home_score)
                if snap.projected_home_score else None,
            "projected_away_score": float(snap.projected_away_score)
                if snap.projected_away_score else None,
            "bookmaker": snap.bookmaker,
        }
        # Include valid_until if available (for deduped rows)
        if hasattr(snap, 'valid_until') and snap.valid_until:
            point["valid_until"] = snap.valid_until.isoformat()
        if hasattr(snap, 'reading_count'):
            point["reading_count"] = snap.reading_count
        history.append(point)
    
    return {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "history": history,
        "points": len(history),
    }


def _format_event(event: Event) -> dict:
    """Format event for API response."""
    return {
        "id": event.id,
        "external_id": event.external_id,
        "sport": event.sport.key if event.sport else None,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "commence_time": event.commence_time.isoformat(),
        "status": event.status,
        "home_score": event.home_score,
        "away_score": event.away_score,
    }


def _format_event_with_odds(event: Event) -> dict:
    """Format event for API response including current odds."""
    response = _format_event(event)

    # Get latest odds snapshot
    if event.odds_snapshots:
        latest_odds = max(
            event.odds_snapshots,
            key=lambda x: x.captured_at
        )
        response["current_odds"] = {
            "bookmaker": latest_odds.bookmaker,
            "captured_at": latest_odds.captured_at.isoformat(),
            "home_moneyline": latest_odds.home_moneyline,
            "away_moneyline": latest_odds.away_moneyline,
            "home_probability": float(latest_odds.home_win_probability)
                if latest_odds.home_win_probability else None,
            "away_probability": float(latest_odds.away_win_probability)
                if latest_odds.away_win_probability else None,
            "spread": float(latest_odds.home_spread)
                if latest_odds.home_spread else None,
            "over_under": float(latest_odds.over_under)
                if latest_odds.over_under else None,
            "projected_home_score": float(latest_odds.projected_home_score)
                if latest_odds.projected_home_score else None,
            "projected_away_score": float(latest_odds.projected_away_score)
                if latest_odds.projected_away_score else None,
        }

    return response


def _format_event_with_latest_odds(event: Event, latest_odds: Optional[OddsSnapshot]) -> dict:
    """Format event for API response with pre-fetched latest odds (memory efficient)."""
    response = _format_event(event)

    if latest_odds:
        response["current_odds"] = {
            "bookmaker": latest_odds.bookmaker,
            "captured_at": latest_odds.captured_at.isoformat(),
            "home_moneyline": latest_odds.home_moneyline,
            "away_moneyline": latest_odds.away_moneyline,
            "home_probability": float(latest_odds.home_win_probability)
                if latest_odds.home_win_probability else None,
            "away_probability": float(latest_odds.away_win_probability)
                if latest_odds.away_win_probability else None,
            "spread": float(latest_odds.home_spread)
                if latest_odds.home_spread else None,
            "over_under": float(latest_odds.over_under)
                if latest_odds.over_under else None,
            "projected_home_score": float(latest_odds.projected_home_score)
                if latest_odds.projected_home_score else None,
            "projected_away_score": float(latest_odds.projected_away_score)
                if latest_odds.projected_away_score else None,
        }

    return response
