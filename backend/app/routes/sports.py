"""Sports API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sport
from app.services import get_db, OddsAPIService

router = APIRouter()

# Excluded sport prefixes (no soccer!)
EXCLUDED_SPORT_PREFIXES = ["soccer_"]


@router.get("")
async def list_sports(db: AsyncSession = Depends(get_db)):
    """
    List all supported sports.

    Returns sports we're actively tracking with their metadata.
    """
    query = select(Sport).where(Sport.active == True)

    # Exclude soccer
    for prefix in EXCLUDED_SPORT_PREFIXES:
        query = query.where(not_(Sport.key.startswith(prefix)))

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
