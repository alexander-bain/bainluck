"""Sports API endpoints."""

import os
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, not_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sport, Event, OddsSnapshot
from app.services import get_db, OddsAPIService

router = APIRouter()

# Excluded sport prefixes (soccer, cricket, rugby, AFL)
EXCLUDED_SPORT_PREFIXES = ["soccer_", "cricket_", "rugbyleague_", "rugbyunion_", "aussierules_"]


@router.get("")
async def list_sports(db: AsyncSession = Depends(get_db)):
    """
    List all supported sports.

    Returns sports we're actively tracking with their metadata.
    """
    query = select(Sport).where(Sport.active == True)

    # Exclude soccer, cricket, rugby, AFL using SQL LIKE
    exclusion_conditions = [Sport.key.like(f"{prefix}%") for prefix in EXCLUDED_SPORT_PREFIXES]
    if exclusion_conditions:
        query = query.where(not_(or_(*exclusion_conditions)))

    result = await db.execute(query.order_by(Sport.name))
    sports = result.scalars().all()

    return {
        "sports": [
            {
                "id": s.id,
                "key": s.key,
                "name": s.name,
                "group": s.group,
            }
            for s in sports
        ]
    }


@router.get("/available")
async def list_available_sports():
    """
    List all sports available from The Odds API.
    
    Useful for discovering new sports to add.
    Note: This hits the external API, so use sparingly.
    """
    try:
        service = OddsAPIService()
        sports = await service.get_sports()
        await service.close()
        
        # Filter to active sports only
        active_sports = [s for s in sports if s.get("active", False)]
        
        return {
            "sports": [
                {
                    "key": s["key"],
                    "group": s["group"],
                    "title": s["title"],
                    "description": s.get("description", ""),
                }
                for s in active_sports
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch sports from API: {str(e)}"
        )


@router.get("/{sport_key}")
async def get_sport(sport_key: str, db: AsyncSession = Depends(get_db)):
    """Get details for a specific sport."""
    result = await db.execute(
        select(Sport).where(Sport.key == sport_key)
    )
    sport = result.scalar_one_or_none()
    
    if not sport:
        raise HTTPException(status_code=404, detail="Sport not found")
    
    return {
        "id": sport.id,
        "key": sport.key,
        "name": sport.name,
        "group": sport.group,
        "active": sport.active,
    }


@router.post("/admin/cleanup-excluded")
async def cleanup_excluded_sports(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove all excluded sports (soccer, cricket, rugby, AFL), events, and odds snapshots.

    This is an admin-only endpoint protected by a secret token.
    """
    # Check admin token
    expected_token = os.getenv("ADMIN_TOKEN", "")
    if not expected_token or x_admin_token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    # Find all excluded sports using LIKE for each prefix
    exclusion_conditions = [Sport.key.like(f"{prefix}%") for prefix in EXCLUDED_SPORT_PREFIXES]
    result = await db.execute(
        select(Sport).where(or_(*exclusion_conditions))
    )
    excluded_sports = result.scalars().all()

    removed_sports = []
    total_events = 0
    total_snapshots = 0

    for sport in excluded_sports:
        # Get events for this sport
        events_result = await db.execute(
            select(Event).where(Event.sport_id == sport.id)
        )
        events = events_result.scalars().all()
        total_events += len(events)

        # Delete odds snapshots for these events
        for event in events:
            snapshot_result = await db.execute(
                delete(OddsSnapshot).where(OddsSnapshot.event_id == event.id)
            )
            total_snapshots += snapshot_result.rowcount or 0

        # Delete events
        await db.execute(
            delete(Event).where(Event.sport_id == sport.id)
        )

        # Delete sport
        removed_sports.append(sport.key)
        await db.delete(sport)

    await db.commit()

    return {
        "removed_sports": removed_sports,
        "removed_events": total_events,
        "removed_snapshots": total_snapshots,
    }
