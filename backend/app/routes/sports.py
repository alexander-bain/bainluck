"""Sports API endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models import Sport
from app.services import get_db, get_db_rw, OddsAPIService
from app.utils.sport_keys import SPORT_HIERARCHY, get_sport_hierarchy


def _check_admin_secret(secret: str) -> bool:
    expected = os.environ.get("ADMIN_TOKEN") or os.environ.get("ADMIN_SECRET")
    return bool(expected and secret == expected)

router = APIRouter()


@router.get("")
async def list_sports(db: AsyncSession = Depends(get_db)):
    """
    List all supported sports.

    Returns sports we're actively tracking with their metadata.
    """
    query = select(Sport).where(Sport.active == True)

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
async def list_available_sports(secret: str = Query(..., description="Admin secret")):
    """List all sports available from The Odds API. Requires admin auth (burns API quota)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
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


@router.post("/sync")
async def sync_sports_from_api(
    secret: str = Query(..., description="Admin secret"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Sync all sports from The Odds API to the database. Requires admin auth."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    try:
        service = OddsAPIService()
        sports_data = await service.get_sports()
        await service.close()

        synced = 0
        skipped = 0

        for sport in sports_data:
            if not sport.get("active", False):
                skipped += 1
                continue

            # Upsert sport
            stmt = insert(Sport).values(
                key=sport["key"],
                name=sport["title"],
                group=sport.get("group"),
                active=True,
            ).on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "name": sport["title"],
                    "group": sport.get("group"),
                    "active": True,
                }
            )
            await db.execute(stmt)
            synced += 1

        await db.commit()

        # Return summary with rugby/cricket/AFL status
        result = await db.execute(
            select(Sport.key, Sport.name)
            .where(Sport.active == True)
            .order_by(Sport.key)
        )
        all_sports = result.all()

        # Check for specific categories
        rugby_sports = [s for s in all_sports if s[0].startswith("rugby")]
        cricket_sports = [s for s in all_sports if s[0].startswith("cricket")]
        afl_sports = [s for s in all_sports if s[0].startswith("aussierules")]

        return {
            "synced": synced,
            "skipped_inactive": skipped,
            "total_in_db": len(all_sports),
            "rugby": {
                "count": len(rugby_sports),
                "sports": [{"key": s[0], "name": s[1]} for s in rugby_sports],
            },
            "cricket": {
                "count": len(cricket_sports),
                "sports": [{"key": s[0], "name": s[1]} for s in cricket_sports],
            },
            "afl": {
                "count": len(afl_sports),
                "sports": [{"key": s[0], "name": s[1]} for s in afl_sports],
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to sync sports from API: {str(e)}"
        )


@router.get("/hierarchy")
async def get_sport_hierarchy_endpoint():
    """
    Get the sport → league navigation tree.

    Returns all sports with their leagues and cross-league showcase events.
    Used by /sport/{sport} hub pages and navigation.
    """
    sports = []
    for slug, data in SPORT_HIERARCHY.items():
        sports.append({
            "slug": data["slug"],
            "name": data["name"],
            "leagues": data["leagues"],
            "showcase_events": data.get("showcase_events", []),
        })
    return {"sports": sports}


@router.get("/hierarchy/{sport_slug}")
async def get_sport_hierarchy_detail(sport_slug: str):
    """
    Get hierarchy data for a single sport.

    Returns leagues and showcase events for the sport hub page.
    """
    hierarchy = get_sport_hierarchy(sport_slug)
    if not hierarchy:
        raise HTTPException(status_code=404, detail=f"Sport '{sport_slug}' not found")
    return {
        "slug": hierarchy["slug"],
        "name": hierarchy["name"],
        "leagues": hierarchy["leagues"],
        "showcase_events": hierarchy.get("showcase_events", []),
    }


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
