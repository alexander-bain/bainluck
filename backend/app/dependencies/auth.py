"""
FastAPI auth dependencies for Firebase token verification.

Two dependency variants:
- get_current_user: requires authentication (returns User or raises 401)
- get_optional_user: returns User if authenticated, None if not

Usage:
    @router.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        ...

    @router.get("/mixed")
    async def mixed(user: Optional[User] = Depends(get_optional_user)):
        if user:
            # personalized response
        else:
            # anonymous response
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services.database import get_db
from app.services.firebase_auth import verify_id_token

logger = logging.getLogger(__name__)

# Optional bearer token — doesn't fail if no token is provided
_bearer_scheme = HTTPBearer(auto_error=False)


async def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
) -> Optional[User]:
    """Verify token and resolve to User. Returns None if not authenticated."""
    if not credentials:
        return None

    claims = verify_id_token(credentials.credentials)
    if not claims:
        return None

    firebase_uid = claims.get("uid")
    if not firebase_uid:
        return None

    # Look up user by firebase_uid
    result = await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require authentication. Returns the User or raises 401."""
    user = await _resolve_user(credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional authentication. Returns User if authenticated, None otherwise."""
    return await _resolve_user(credentials, db)
