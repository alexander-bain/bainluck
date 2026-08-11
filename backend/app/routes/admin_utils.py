"""Shared utilities for admin endpoints."""

import hashlib
import hmac
import logging
import os

from fastapi import Request
from sqlalchemy import select

_logger = logging.getLogger(__name__)

# Header carrying the second token for destructive operations (Queue 315 Item 2).
# A header, not a query param: gotcha-adjacent to Queue #252 Item 3, which removed
# `?secret=` because a secret in the URL leaks through browser history, the Referer
# header, access logs and shared links. A second secret must not re-open that.
DESTRUCTIVE_TOKEN_HEADER = "X-Admin-Destructive-Token"


def bearer_credentials(request: Request | None) -> str:
    """Return the credentials from ``Authorization: Bearer <token>``, or ``""``.

    The scheme is matched CASE-INSENSITIVELY (Queue 332 Item 3). RFC 9110 §11.1
    defines auth-scheme as case-insensitive, and more concretely: the rate-limit
    boundary already lowercases this exact prefix (``app/utils/rate_limit.py:412``,
    ``auth_header.lower().startswith("bearer ")``) before assigning the 300/min
    admin bucket. While this parser required a capital ``Bearer``, one identical
    request was classified INTO the admin bucket by one boundary and rejected 403
    by the other. Two readings of one request is the bug — not either reading.

    Parsing lives here, once, so the two boundaries cannot drift apart again. The
    token comparison stays exact and constant-time; only the scheme is lenient.
    """
    if request is None:
        return ""
    auth_header = request.headers.get("authorization", "")
    scheme, separator, credentials = auth_header.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return ""
    return credentials.strip()


def _tokens_match(presented: str | None, expected: str | None) -> bool:
    """Constant-time token equality.

    ``hmac.compare_digest`` over UTF-8 bytes rather than ``==``: a plain string
    compare short-circuits on the first differing byte, so its timing leaks a
    prefix-length oracle to anyone who can measure it. Encoding first also avoids
    ``compare_digest``'s TypeError on non-ASCII str inputs, which a caller
    controls by simply sending a non-ASCII token.
    """
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def _hash_for_audit(value: str | None) -> str:
    """Short sha256 for audit lines. Never log the value itself."""
    if not value:
        return "none"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def audit_admin_call(
    request: Request,
    *,
    kind: str,
    sql: str | None = None,
) -> None:
    """Emit exactly ONE structured INFO line for a sensitive admin call.

    Queue 315 Item 3. Logs the route, the method and HASHES of the query string
    and (for db-query) the SQL — never their contents.

    The hashing is the point, not caution for its own sake: an audit log that
    recorded SQL text or parameter values would become the exfiltration path that
    the rate limit and the second token were added to close. Anyone who can read
    logs would get the data without ever holding a token. Hashes still answer the
    questions an audit log exists to answer — *was this called, how often, and was
    it the same call repeated or a new one each time* — which is what you need at
    3am when a token may have leaked.
    """
    _logger.info(
        "admin_audit kind=%s method=%s route=%s params_hash=%s sql_hash=%s",
        kind,
        request.method,
        request.url.path,
        _hash_for_audit(request.url.query),
        _hash_for_audit(sql),
    )


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
    if _tokens_match(bearer_credentials(request), expected):
        return True

    if secret:
        _logger.warning(
            "Rejected deprecated ?secret= query-param admin auth; "
            "use 'Authorization: Bearer <token>'"
        )

    raise HTTPException(status_code=403, detail="Invalid admin secret")


def _check_admin_destructive(
    secret: str | None = None, *, request: Request | None = None
) -> bool:
    """Auth gate for DESTRUCTIVE admin mutations: ``ADMIN_TOKEN`` **and**
    ``ADMIN_TOKEN_DESTRUCTIVE``.

    Queue 315 Item 2. The standing ruling is that destructive operations are
    attended-only. Until now that was enforced by everyone remembering it; this is
    the mechanism that makes it true. Agent lanes are issued ``ADMIN_TOKEN`` and
    NOT ``ADMIN_TOKEN_DESTRUCTIVE``, so a lane physically cannot run one of these
    routes no matter what it decides to do.

    WHY THE TOKEN PATH ONLY (P5 — the queue's central design decision):
    ``_check_admin_auth`` accepts either the admin token or a Firebase admin
    identity. Only the token path is gated here. A Firebase identity is Alex in a
    browser, which is attended *by construction* — gating it would break the admin
    UI for the one person the attended-only ruling exists to keep in the loop.
    In practice this is currently moot and worth knowing: **every route in the
    destructive set authenticates via the token path only** (none of them call
    ``_check_admin_auth``), so today this gate covers the whole set. If a
    destructive route ever adopts the identity path, revisit this deliberately
    rather than discovering it.

    Raises HTTPException(403) on failure, naming the missing/mismatched env var —
    the failure will be met by Alex mid-operation, and a generic denial would tell
    him nothing about what to do next. Returns True on success.
    """
    from fastapi import HTTPException

    # Base token first: a caller without it learns nothing about the second one.
    _check_admin_secret(secret, request=request)

    expected = os.getenv("ADMIN_TOKEN_DESTRUCTIVE")
    if not expected:
        raise HTTPException(
            status_code=403,
            detail=(
                "This endpoint is destructive and requires a second token, but "
                "ADMIN_TOKEN_DESTRUCTIVE is not configured on the server. Set it "
                "with: heroku config:set ADMIN_TOKEN_DESTRUCTIVE=<value> -a bainluck"
            ),
        )

    presented = ""
    if request is not None:
        presented = (request.headers.get(DESTRUCTIVE_TOKEN_HEADER, "") or "").strip()

    if not presented:
        raise HTTPException(
            status_code=403,
            detail=(
                f"This endpoint is destructive. ADMIN_TOKEN alone is not "
                f"sufficient: also send the '{DESTRUCTIVE_TOKEN_HEADER}' header "
                f"with the value of $ADMIN_TOKEN_DESTRUCTIVE."
            ),
        )

    if not _tokens_match(presented, expected):
        raise HTTPException(
            status_code=403,
            detail=(
                f"The '{DESTRUCTIVE_TOKEN_HEADER}' header does not match "
                f"ADMIN_TOKEN_DESTRUCTIVE."
            ),
        )

    if request is not None:
        audit_admin_call(request, kind="destructive")
    return True


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
    token = bearer_credentials(request)
    if token:
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
    token = bearer_credentials(request)
    if not token:
        return None
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
