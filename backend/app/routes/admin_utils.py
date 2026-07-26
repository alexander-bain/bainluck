"""Shared utilities for admin endpoints."""

import logging
import os

from fastapi import Request
from sqlalchemy import select

_logger = logging.getLogger(__name__)


def _safe_send_task(task_name: str, *args, **kwargs):
    """Enqueue a Celery task, converting a transient broker/transport failure
    into a clean retryable 503 instead of an opaque 500.

    Auth + validation happen at the call site before this runs, so a 503 here
    means only "broker temporarily unavailable; retry". Forwards *args/**kwargs
    (queue=, args=, kwargs=, countdown=, ...) verbatim to celery_app.send_task so
    task name, queue routing, and payload are preserved. (Queue #256 Item 2 —
    generalizes Queue #255's calibration-recompute-only fix to every admin enqueue.)
    """
    from fastapi import HTTPException
    from app.tasks import celery_app
    try:
        return celery_app.send_task(task_name, *args, **kwargs)
    except Exception as exc:  # kombu OperationalError + any broker/transport error
        _logger.warning("Enqueue failed for %s: %s", task_name, exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "Task broker is temporarily unavailable; the job was not enqueued. "
                "Please retry shortly."
            ),
        ) from exc


def _check_admin_secret(secret: str | None = None, *, request: Request | None = None) -> bool:
    """Verify the admin token for protected endpoints.

    Accepts the token ONLY via the ``Authorization: Bearer <token>`` header.

    SECURITY (Queue #252 Item 3): the legacy ``?secret=`` query-parameter path is
    REMOVED. A secret in the URL leaks through browser history, the Referer
    header, server access logs, and shared links. The ``secret`` argument is
    retained purely for call-site signature compatibility (many endpoints still
    declare ``secret: str = Query(...)``) but it is no longer honored for auth —
    a request that supplies only ``?secret=`` is rejected.

    Raises HTTPException(403) on failure. Returns True on success.
    """
    from fastapi import HTTPException

    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if not expected:
        raise HTTPException(status_code=403, detail="Admin auth not configured")

    # Authorization header is the ONLY accepted transport.
    if request is not None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == expected:
                return True

    if secret:
        _logger.warning(
            "Rejected deprecated ?secret= query-param admin auth; "
            "use 'Authorization: Bearer <token>'"
        )

    raise HTTPException(status_code=403, detail="Invalid admin secret")


DEFAULT_ADMIN_USER_IDS = {364}
DEFAULT_ADMIN_EMAILS: set[str] = set()


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
    # 1. ADMIN_TOKEN via Authorization: Bearer header. Queue #252 Item 4: this
    #    must work even when no ?secret= query value is present — identity-aware
    #    endpoints previously only tried this when `secret` was truthy, so the
    #    preferred header form was rejected. _check_admin_secret raises on
    #    mismatch, so guard it and fall through to the identity check.
    try:
        if _check_admin_secret(secret, request=request):
            return True
    except Exception:
        pass
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
