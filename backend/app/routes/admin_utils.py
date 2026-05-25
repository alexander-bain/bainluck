"""Shared utilities for admin endpoints."""

import os

from fastapi import Request
from sqlalchemy import select


def _check_admin_secret(secret: str | None) -> bool:
    """Verify admin secret for protected endpoints.

    Checks ADMIN_TOKEN (canonical, set on Heroku) with ADMIN_SECRET as
    fallback for backward compatibility. See gotchas-reference.md #40.
    """
    if not secret:
        return False
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if not expected:
        return False
    return secret == expected


DEFAULT_ADMIN_USER_IDS = {364}
DEFAULT_ADMIN_EMAILS = {"alex.bain@gmail.com", "alex.bain@bainluck.com", "olivercbain@gmail.com", "daphnegardinerbain@gmail.com", "dexterhbain@gmail.com"}


def _admin_user_ids() -> set[int]:
    values = set(DEFAULT_ADMIN_USER_IDS)
    raw = os.getenv("ADMIN_USER_IDS", "")
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.add(int(part))
        except ValueError:
            continue
    return values


def _admin_user_emails() -> set[str]:
    values = set(DEFAULT_ADMIN_EMAILS)
    raw = os.getenv("ADMIN_USER_EMAILS", "")
    values.update(part.strip().lower() for part in raw.split(",") if part.strip())
    return values


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
                    if user and (
                        user.id in _admin_user_ids()
                        or (user.email or "").lower() in _admin_user_emails()
                    ):
                        return True
        except Exception:
            pass
    return False


async def _resolve_admin_email(request: Request, db=None) -> str | None:
    """Extract the authenticated admin user's email from a Bearer token.

    Returns the email string when the request carries a valid admin Bearer
    token, or ``None`` when the caller is not authenticated or not an admin.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from app.services.firebase_auth import verify_id_token

        claims = verify_id_token(token)
        if not claims:
            return None
        firebase_uid = claims.get("uid") or claims.get("sub")
        if not firebase_uid or not db:
            return None
        from app.models.models import User

        result = await db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        user = result.scalar_one_or_none()
        if user and (
            user.id in _admin_user_ids()
            or (user.email or "").lower() in _admin_user_emails()
        ):
            return (user.email or "").lower() or None
    except Exception:
        pass
    return None
