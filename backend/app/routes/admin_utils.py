"""Shared utilities for admin endpoints."""

import os

from fastapi import Request
from sqlalchemy import select


def _check_admin_secret(secret: str) -> bool:
    """Verify admin secret for protected endpoints.

    Checks ADMIN_TOKEN (canonical, set on Heroku) with ADMIN_SECRET as
    fallback for backward compatibility. See gotchas-reference.md #40.
    """
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if not expected:
        return False
    return secret == expected


ADMIN_USER_IDS = {364}


async def _check_admin_auth(secret: str | None, request: Request, db=None) -> bool:
    if secret and _check_admin_secret(secret):
        return True
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from app.services.firebase_auth import verify_id_token
            claims = verify_id_token(token)
            if claims:
                firebase_uid = claims.get("uid") or claims.get("sub")
                if firebase_uid and db:
                    from app.models.models import User
                    result = await db.execute(
                        select(User).where(User.firebase_uid == firebase_uid)
                    )
                    user = result.scalar_one_or_none()
                    if user and user.id in ADMIN_USER_IDS:
                        return True
        except Exception:
            pass
    return False
