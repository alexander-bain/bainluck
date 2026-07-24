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
from app.services.database import get_db_rw
from app.services.firebase_auth import verify_id_token

logger = logging.getLogger(__name__)

# Optional bearer token — doesn't fail if no token is provided
_bearer_scheme = HTTPBearer(auto_error=False)


async def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
) -> Optional[User]:
    """Verify token and resolve to User. Returns None if not authenticated.

    Safety net: if the token is valid but no User record exists in the DB
    (e.g., because the background registerWithBackend call failed after sign-in),
    auto-creates the User record so authenticated requests don't fail with 401.
    """
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

    # SECURITY (Queue #252 Item 2): do NOT auto-create a User from a token that
    # has no matching DB row. The old "safety net" resurrected DELETED accounts —
    # a user could DELETE /me and their still-valid 30-day session token would
    # silently re-create the account on the next request, so deletion never
    # revoked anything. It also minted a User from *any* valid-looking claim.
    # A token with no user now resolves to None -> 401. Legitimate sign-ins
    # create the User row synchronously in /google, /apple and
    # /google-access-token, so no real user depends on this path; if a client's
    # registration genuinely failed, re-authenticating recreates the row.
    if user is None:
        logger.info(
            "Rejecting token with no matching User row "
            "(deleted account or unregistered): uid=%s",
            firebase_uid,
        )
        return None

    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
) -> Optional[User]:
    """Optional authentication. Returns User if authenticated, None otherwise."""
    return await _resolve_user(credentials, db)
