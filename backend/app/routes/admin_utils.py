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


def _check_admin_secret(
    secret: str | None = None,
    *,
    request: Request | None = None,
    allow_account: bool = True,
) -> bool:
    """Verify the caller's admin authorization for protected endpoints.

    Two credentials are accepted, both via ``Authorization: Bearer <token>``:

    1. **The machine token** (``ADMIN_TOKEN``) — lanes, scripts, the bus.
    2. **A signed-in admin account** (#5952) — the Google account Alex is
       already signed into Bain Luck with. The token is verified and resolved to
       a ``User`` row by ``admin_account_identity``, the router-level dependency
       on every admin router, which leaves the result on ``request.state``. This
       function only *reads* that decision: authorization is decided server-side
       from the allowlist, never from anything the client asserts about itself.

    The token is tried first, so machine callers are unaffected and pay no
    Firebase/DB cost, and an admin account is consulted only when the token
    path has already failed.

    ``allow_account=False`` restricts the check to the machine token alone. It
    exists for ``_check_admin_destructive``, whose docstring asked for exactly
    this decision to be made deliberately rather than discovered — see there.

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

    # Authorization header is the ONLY accepted transport.
    if expected and _tokens_match(bearer_credentials(request), expected):
        return True

    # #5952: a verified, allowlisted account session. Checked before the
    # "not configured" refusal below so that an admin account still works on a
    # deployment with no ADMIN_TOKEN set — the account path does not depend on
    # that env var existing.
    if allow_account and account_admin_email(request):
        return True

    if not expected:
        raise HTTPException(status_code=403, detail="Admin auth not configured")

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
    the base check here is made with ``allow_account=False``, so a destructive
    route requires the machine ``ADMIN_TOKEN`` **and** ``ADMIN_TOKEN_DESTRUCTIVE``
    — a signed-in admin *account* alone is not sufficient.

    REVISITED DELIBERATELY (#5952). The previous text recorded that only the
    token path was gated here, that this was moot because no destructive route
    used the identity path, and that "if a destructive route ever adopts the
    identity path, revisit this deliberately rather than discovering it". #5952
    is that moment: it gives *every* admin route an account path, so the whole
    destructive set adopted it at once. The decision is to hold the line where
    it is. #5952's ship is that Alex stops typing a second password to *read*
    the dashboard; it is not a request to widen who can run a destructive
    mutation, and a browser session is a materially weaker credential than the
    machine token (it rides a 30-day session token on the Safari fallback, it
    is the thing an XSS or a borrowed laptop gets). Silently promoting it to
    destructive authority would have been a privilege increase nobody asked
    for, delivered as a side effect of a convenience ship. The attended-only
    ruling is unchanged and the set is still exactly ``ADMIN_TOKEN`` holders.

    Raises HTTPException(403) on failure, naming the missing/mismatched env var —
    the failure will be met by Alex mid-operation, and a generic denial would tell
    him nothing about what to do next. Returns True on success.
    """
    from fastapi import HTTPException

    # Base token first: a caller without it learns nothing about the second one.
    _check_admin_secret(secret, request=request, allow_account=False)

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


# ---------------------------------------------------------------------------
# Account admin identity (#5952)
# ---------------------------------------------------------------------------

#: Where ``admin_account_identity`` leaves its decision for ``_check_admin_secret``.
#: A private attribute name on ``request.state`` rather than a header or a
#: contextvar: it is per-request by construction, it cannot be set by a client,
#: and it dies with the request.
ACCOUNT_ADMIN_STATE_ATTR = "_bainluck_account_admin_email"


def account_admin_email(request: Request | None) -> str | None:
    """The admin email ``admin_account_identity`` resolved for THIS request.

    ``None`` when the caller is anonymous, is signed in but not an admin, or
    when the request never went through the dependency (a router that does not
    mount it, or a unit test constructing a bare ``Request``). ``None`` is
    always a denial here, never a fallback — a route that cannot tell whether
    the caller is an admin must ask for the machine token.
    """
    if request is None:
        return None
    # `getattr` twice, not `request.state`: a hand-built stand-in for a Request
    # (several suites pass a SimpleNamespace carrying only `headers`) has no
    # `.state`, and an AttributeError raised out of the gate would turn "this
    # caller is not an account admin" into a 500. Absent state reads as "no
    # account admin", which is the closed answer.
    state = getattr(request, "state", None)
    return getattr(state, ACCOUNT_ADMIN_STATE_ATTR, None)


async def admin_account_identity(request: Request) -> None:
    """Router-level dependency: resolve the signed-in account's admin identity.

    Mounted on every admin router in ``main.py`` (see ``ADMIN_ROUTER_DEPENDENCIES``
    there) so that the ~390 routes gated by ``_check_admin_secret`` — which is
    synchronous and has no database — can nonetheless authorize a Google account
    session. The async, DB-touching half happens here, once per request, and
    leaves a plain string on ``request.state`` for the sync gate to read.

    THREE PROPERTIES, ALL LOAD-BEARING:

    * **It never raises.** It is an identity resolver, not a gate. A request
      that is not an admin session must still reach its route so the route's own
      ``_check_admin_secret`` can refuse it with the 403 it has always returned.
      Raising here would turn every unauthenticated admin call into a different
      error shape, and would make an outage in Firebase an outage in the machine
      token path.
    * **The machine token short-circuits it.** A request already carrying
      ``ADMIN_TOKEN`` is going to be authorized by the token branch of
      ``_check_admin_secret`` regardless, so it pays no Firebase verification
      and no query. Lanes and the bus are the overwhelming majority of admin
      traffic and are unaffected by this ship.
    * **It is scoped to admin paths.** The dependency is cheap to mount on a
      mixed router (``notifications`` has four admin routes among its public
      ones) because a non-admin path returns before doing any work.

    It takes no ``db`` dependency ON PURPOSE. A ``Depends(get_db)`` here would be
    resolved eagerly, opening a session on every admin request including the
    machine-token ones this function does no work for; and any non-``Depends``
    parameter would be read by FastAPI as a query parameter on all ~390 routes.
    So it opens its own short-lived read session, and only on the one path that
    needs it. ``_stamp_account_admin`` carries the logic and accepts an injected
    session for tests.
    """
    await _stamp_account_admin(request)


async def _stamp_account_admin(request: Request, db=None) -> str | None:
    """The body of ``admin_account_identity``; ``db=None`` opens its own session.

    Returns the email it stamped (or ``None``), which the dependency discards
    and tests assert on.
    """
    if "/admin" not in request.url.path:
        return None
    token = bearer_credentials(request)
    if not token:
        return None
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if expected and _tokens_match(token, expected):
        return None

    try:
        if db is not None:
            email = await _resolve_admin_email(request, db)
        else:
            from app.services.database import async_session_maker

            async with async_session_maker() as session:
                email = await _resolve_admin_email(request, session)
    except Exception:
        # Never raise out of a router-level dependency: a database or Firebase
        # failure must not change the shape of an unrelated admin request, and
        # must not take the machine-token path down with it.
        _logger.warning("Account-admin identity resolution failed", exc_info=True)
        return None

    if email:
        setattr(request.state, ACCOUNT_ADMIN_STATE_ATTR, email)
        return email
    return None


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


async def resolve_bearer_user_email(request: Request, db=None) -> str | None:
    """The signed-in caller's email — WITHOUT asking whether they are an admin.

    ``_resolve_admin_email`` answers "who is this, if they are allowlisted"; this
    answers "who is this". The distinction is what lets a route authorize by
    OWNERSHIP rather than by privilege: a reviewer retracting their own row is
    not exercising an admin capability, and requiring one to do it is how the
    judgment-undo path ended up unusable from the surface that writes judgments
    (UX-P125 item 3a).

    Accepts either a Firebase ID token or a backend-issued session token — the
    iOS app carries the latter, and a helper that quietly handled only the
    former would return ``None`` for every real device and look exactly like
    "not signed in".

    Returns a lowercased email, or ``None`` when the caller is anonymous, the
    token does not verify, or no ``User`` row matches it. A ``None`` here is
    never an authorization decision on its own — it means the caller has no
    identity to compare against, so the route must fall back to its own gate.
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
        if not firebase_uid or db is None:
            return None
        from app.models.models import User

        result = await db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        return (user.email or "").strip().lower() or None
    except Exception:
        return None
