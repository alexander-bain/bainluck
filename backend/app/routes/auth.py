"""
Authentication routes.

Handles Firebase ID token verification, user creation/lookup,
and profile management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_current_user
from app.models.models import User, UserPreference
from app.services.database import get_db
from app.services.firebase_auth import verify_id_token, is_configured

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Request/Response schemas ---

class GoogleAuthRequest(BaseModel):
    """Request body for Google sign-in."""
    id_token: str


class UserProfileResponse(BaseModel):
    """User profile returned to frontend."""
    id: int
    email: Optional[str]
    display_name: Optional[str]
    photo_url: Optional[str]
    onboarding_completed: bool
    created_at: str

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    """Request body for profile updates."""
    display_name: Optional[str] = None


# --- Endpoints ---

@router.get("/status")
async def auth_status():
    """Check if authentication is configured."""
    return {
        "auth_configured": is_configured(),
        "providers": ["google"] if is_configured() else [],
    }


@router.post("/google", response_model=UserProfileResponse)
async def google_sign_in(
    body: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a Firebase ID token from Google Sign-In and return the user profile.
    Creates a new user if this is the first sign-in.
    """
    claims = verify_id_token(body.id_token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    firebase_uid = claims.get("uid")
    email = claims.get("email")
    name = claims.get("name")
    picture = claims.get("picture")

    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing uid claim",
        )

    # Look up or create user
    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update profile fields from Google on each sign-in
        if email:
            user.email = email
        if name and not user.display_name:
            user.display_name = name
        if picture:
            user.photo_url = picture
    else:
        # Create new user
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            display_name=name,
            photo_url=picture,
        )
        db.add(user)
        await db.flush()  # Get the user.id

        # Create empty preferences
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)

    onboarding_completed = False
    if user.preferences:
        onboarding_completed = user.preferences.onboarding_completed

    logger.info(f"User signed in: uid={firebase_uid}, email={email}")

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        onboarding_completed=onboarding_completed,
        created_at=user.created_at.isoformat(),
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile."""
    # Load preferences relationship
    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.id == user.id)
    )
    user = result.scalar_one()

    onboarding_completed = False
    if user.preferences:
        onboarding_completed = user.preferences.onboarding_completed

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        onboarding_completed=onboarding_completed,
        created_at=user.created_at.isoformat(),
    )


@router.patch("/me", response_model=UserProfileResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    if body.display_name is not None:
        user.display_name = body.display_name

    # Re-fetch with preferences
    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.id == user.id)
    )
    user = result.scalar_one()

    onboarding_completed = False
    if user.preferences:
        onboarding_completed = user.preferences.onboarding_completed

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        onboarding_completed=onboarding_completed,
        created_at=user.created_at.isoformat(),
    )


@router.delete("/me")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the current user's account and all associated data."""
    await db.delete(user)
    logger.info(f"User account deleted: id={user.id}")
    return {"status": "deleted"}
