"""
User data routes: pins, preferences, team search.

All endpoints require authentication.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.models.models import User, UserPin, Team
from app.services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---

class PinsResponse(BaseModel):
    """All pinned items for a user."""
    events: list[int]
    futures: list[int]


class AddPinRequest(BaseModel):
    """Add a single pin."""
    pin_type: str  # "event" or "future"
    target_id: int


class BulkPinsRequest(BaseModel):
    """Bulk upsert pins (for localStorage migration)."""
    events: list[int] = []
    futures: list[int] = []


class TeamSearchResult(BaseModel):
    """Team search result for autocomplete."""
    id: int
    name: str
    location: Optional[str]
    sport_key: Optional[str]
    logo_url: Optional[str]
    abbreviation: Optional[str]


# --- Pin endpoints ---

MAX_PINS_PER_TYPE = 25  # More generous server-side limit than the 6 in localStorage


@router.get("/pins", response_model=PinsResponse)
async def get_pins(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all pinned event and futures IDs for the current user."""
    result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    pins = result.scalars().all()

    return PinsResponse(
        events=[p.target_id for p in pins if p.pin_type == "event"],
        futures=[p.target_id for p in pins if p.pin_type == "future"],
    )


@router.put("/pins", response_model=PinsResponse)
async def bulk_upsert_pins(
    body: BulkPinsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk upsert pins. Used for migrating localStorage pins to the database.
    Merges with existing pins (doesn't delete unmentioned pins).
    """
    # Get existing pins
    result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    existing = result.scalars().all()
    existing_keys = {(p.pin_type, p.target_id) for p in existing}

    # Add new event pins
    for event_id in body.events[:MAX_PINS_PER_TYPE]:
        if ("event", event_id) not in existing_keys:
            db.add(UserPin(user_id=user.id, pin_type="event", target_id=event_id))

    # Add new futures pins
    for future_id in body.futures[:MAX_PINS_PER_TYPE]:
        if ("future", future_id) not in existing_keys:
            db.add(UserPin(user_id=user.id, pin_type="future", target_id=future_id))

    await db.flush()

    # Return the merged result
    result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    pins = result.scalars().all()

    return PinsResponse(
        events=[p.target_id for p in pins if p.pin_type == "event"],
        futures=[p.target_id for p in pins if p.pin_type == "future"],
    )


@router.post("/pins", status_code=status.HTTP_201_CREATED)
async def add_pin(
    body: AddPinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a single pin."""
    if body.pin_type not in ("event", "future"):
        raise HTTPException(status_code=400, detail="pin_type must be 'event' or 'future'")

    # Check limit
    result = await db.execute(
        select(UserPin).where(
            and_(UserPin.user_id == user.id, UserPin.pin_type == body.pin_type)
        )
    )
    current_count = len(result.scalars().all())
    if current_count >= MAX_PINS_PER_TYPE:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PINS_PER_TYPE} pins per type")

    # Check for duplicate
    result = await db.execute(
        select(UserPin).where(
            and_(
                UserPin.user_id == user.id,
                UserPin.pin_type == body.pin_type,
                UserPin.target_id == body.target_id,
            )
        )
    )
    if result.scalar_one_or_none():
        return {"status": "already_pinned"}

    db.add(UserPin(
        user_id=user.id,
        pin_type=body.pin_type,
        target_id=body.target_id,
    ))

    return {"status": "pinned"}


@router.delete("/pins/{pin_type}/{target_id}")
async def remove_pin(
    pin_type: str,
    target_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a pin."""
    if pin_type not in ("event", "future"):
        raise HTTPException(status_code=400, detail="pin_type must be 'event' or 'future'")

    await db.execute(
        delete(UserPin).where(
            and_(
                UserPin.user_id == user.id,
                UserPin.pin_type == pin_type,
                UserPin.target_id == target_id,
            )
        )
    )

    return {"status": "unpinned"}


# --- Team search (for onboarding autocomplete) ---

@router.get("/teams/search", response_model=list[TeamSearchResult])
async def search_teams(
    q: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Search teams by name for autocomplete.
    Does not require auth — used during onboarding flow.
    Searches team name, alternate_names, and location.
    """
    if len(q) < 2:
        return []

    search_pattern = f"%{q}%"

    # Search by name or location (ILIKE for case-insensitive)
    from app.models.models import Sport
    result = await db.execute(
        select(Team, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id)
        .where(
            Team.name.ilike(search_pattern)
            | Team.location.ilike(search_pattern)
        )
        .order_by(Team.name)
        .limit(20)
    )
    rows = result.all()

    return [
        TeamSearchResult(
            id=team.id,
            name=team.name,
            location=team.location,
            sport_key=sport_key,
            logo_url=team.logo_url_small or team.logo_url,
            abbreviation=team.abbreviation,
        )
        for team, sport_key in rows
    ]
