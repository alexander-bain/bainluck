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

    AMENDED Queue 386 Item 2 (Alex ruling 2026-08-20), which broadened identity
    admin from a hardcoded id set to a ``users.is_admin`` column and unblocked
    the admin UI for an identity session. **Identity alone still NEVER unlocks a
    delete**, and the mechanism is the first line of the body rather than a
    policy anyone has to remember: this function calls ``_check_admin_secret``,
    which is token-only. An identity-authenticated request fails there and never
    reaches the second token at all. ``tests/test_admin_identity_auth_q386.py``
    pins that — an admin-by-identity request against a destructive endpoint is
    403 even with a correct ``X-Admin-Destructive-Token``.

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


def _user_is_admin(user) -> bool:
    """Whether this ``User`` row holds the admin role.

    Queue 386 Item 2 (Alex ruling 2026-08-20). Three sources, checked in this
    order, all OR-ed:

    1. ``users.is_admin`` — the SERVER-SIDE role, the one that is meant to
       outlive the other two. A grant is one UPDATE, a revocation is one UPDATE,
       and ``SELECT id, email FROM users WHERE is_admin`` answers *who is an
       admin right now* without reading source code.
    2. ``ADMIN_USER_IDS`` / the hardcoded ``DEFAULT_ADMIN_USER_IDS``.
    3. ``ADMIN_USER_EMAILS`` / ``DEFAULT_ADMIN_EMAILS``.

    (2) and (3) are the pre-existing allowlists and are deliberately KEPT rather
    than replaced. The column ships in a release; the grant is a separate manual
    UPDATE Alex runs afterwards. Deleting the allowlists in the same change would
    open a window — however short — in which the admin UI has no admin, and the
    person locked out is the one holding the SQL.

    THE COLUMN IS AUTHORITATIVE IN BOTH DIRECTIONS (Queue 390, C-2063-REVIEW
    finding 2). This function previously OR-ed the allowlists *after* the column,
    which made the advertised revocation decorative for the one row the feature
    was built for: ``DEFAULT_ADMIN_USER_IDS = {364}``, so
    ``UPDATE users SET is_admin = false WHERE id = 364`` changed nothing and a
    compromised session stayed admin until someone shipped code. The reviewer
    executed it — a civilian JWT on row ``364, is_admin=False`` got
    ``200 {is_admin: true, via: "identity"}``.

    So the column is now read as THREE states, and the third is why the column
    had to become nullable:

    * ``True``  — granted. Admin, no allowlist needed.
    * ``False`` — REVOKED. Denied, and the legacy allowlists do not get a vote.
    * absent / ``None`` — *no decision recorded*. Only here do the allowlists
      apply, which is exactly the rollout window they exist for.

    Two states cannot express this. Under the original
    ``BOOLEAN NOT NULL DEFAULT false`` every pre-existing row reads ``false`` the
    moment the release lands, so "explicit false denies" and "the allowlists still
    work before the grant" are contradictory. ``NULL`` is what separates *nobody
    has decided* from *somebody decided no*.

    ``__dict__.get`` rather than ``getattr``: ``getattr`` on an ORM attribute that
    was expired or never loaded triggers a lazy refresh, which raises
    ``MissingGreenlet`` in an async context (a repeat failure in this codebase).
    ``__dict__`` reads only what the SELECT actually loaded. Note this folds
    "column not loaded" into the same reading as SQL ``NULL`` — deliberately: a
    SELECT that did not fetch the column has not shown us a revocation, and
    inventing one would deny an admin for a query-shape reason.
    """
    if user is None:
        return False
    explicit = user.__dict__.get("is_admin")
    if explicit is True:
        return True
    if explicit is False:
        # An explicit revocation. Terminal — this is the whole point of the
        # column, and a fallback that could override it would put the grant back
        # in source code where it cannot be audited or revoked.
        return False
    if user.id in _admin_user_ids():
        return True
    return (user.email or "").lower() in _admin_user_emails()


async def _resolve_admin_user(request: Request, db=None):
    """Resolve the Bearer token to an ADMIN ``User`` row, or ``None``.

    This is the identity arm, factored out so ``_check_admin_auth`` and
    ``_resolve_admin_email`` cannot drift — the reason it exists is that they had
    already grown two hand-copied versions of the same lookup, and a privilege
    check duplicated is a privilege check that will eventually disagree with
    itself about who is an admin.

    Returns ``None`` for every failure mode — no token, an unverifiable token, a
    token for a user with no row, a real user who is not an admin. The caller
    cannot distinguish them, which is deliberate: a 403 that says *which arm
    failed* is an oracle for probing who has admin.
    """
    token = bearer_credentials(request)
    if not token or db is None:
        return None
    try:
        from app.services.firebase_auth import verify_id_token

        claims = verify_id_token(token)
        if not claims:
            return None
        firebase_uid = claims.get("uid") or claims.get("sub")
        if not firebase_uid:
            return None
        from app.models.models import User

        result = await db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        user = result.scalar_one_or_none()
        if user is not None and _user_is_admin(user):
            return user
    except Exception:
        # Any failure in the identity arm is a non-admin, never an error. This
        # arm runs AFTER the token arm has already declined, so swallowing here
        # can only ever turn a would-be 500 into the 403 the caller was getting
        # anyway — it can never upgrade a rejection into an acceptance.
        pass
    return None


class AdminPrincipal:
    """WHO authorized this request, and by WHICH arm.

    DELIBERATELY NOT A ``@dataclass``, and this comment exists so the next reader
    does not "clean it up" into one. ``scripts/evals/admin_auth_gate_mutations.py``
    exercises the auth gate by ``exec``-ing this module's source into a synthetic
    module that is never registered in ``sys.modules`` — on purpose, so a mutated
    (deliberately weakened) copy of the auth gate can never leak into the shared
    module table. ``@dataclass`` resolves annotations via
    ``sys.modules.get(cls.__module__).__dict__``, which is ``None`` under that
    loader, so decorating this class turns all eight auth-mutation evals into
    collection ERRORS — pytest exit 2, the "could not check" code (gotcha #54).
    A hand-written ``__init__`` costs four lines and keeps the mutation evals
    able to load the thing they exist to attack.

    Queue 390 (``C-2063-REVIEW`` findings 3 and 4). Authorization used to return
    a bare ``bool``, so a handler that needed to know *who* had authorized had no
    way to ask and simply re-ran the identity resolution against the same bearer.
    Two defects fell out of that one shape:

    * the shared-ADMIN_TOKEN path re-entered Firebase verification on every label
      write — the "lanes keep tokens, zero change to their path" claim was true of
      the gate and false of the request; and
    * attribution had no authoritative record of which arm won, so it guessed
      from the caller-supplied ``reviewer`` string, which the caller controls.

    A boolean cannot carry a principal. This can.

    ``via`` is ``"token"`` (the shared capability — identifies nobody, so
    ``user`` and ``email`` are ``None`` and that absence is the honest encoding)
    or ``"identity"`` (a verified session of a user holding the admin role).
    """

    __slots__ = ("via", "user", "email")

    def __init__(self, via: str, user=None, email: str | None = None):
        self.via = via
        self.user = user
        self.email = email

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        # Never renders the user row or anything token-shaped.
        return f"AdminPrincipal(via={self.via!r}, email={self.email!r})"


async def _resolve_admin_principal(
    secret: str | None, request: Request, db=None
) -> "AdminPrincipal | None":
    """Resolve admin authorization ONCE, into a principal rather than a boolean.

    ORDER IS LOAD-BEARING and is unchanged from ``_check_admin_auth``: the token
    arm is a constant-time ``compare_digest`` against an env var and runs FIRST,
    with no database, no JWT parse and no network. When it wins, this function
    RETURNS — the identity arm is never reached, which is what makes the lanes'
    path mechanically the same as before rather than the same by promise.

    Returns ``None`` when neither arm authorizes. Callers must not be able to
    distinguish which arm declined; a 403 that discloses that is an oracle for
    probing who holds admin.
    """
    # 1. The shared capability. Cheapest, and terminal on success.
    try:
        if _check_admin_secret(secret, request=request):
            return AdminPrincipal(via="token")
    except Exception:
        pass
    # 2. A verified session belonging to a user carrying the admin role.
    user = await _resolve_admin_user(request, db)
    if user is None:
        return None
    return AdminPrincipal(
        via="identity",
        user=user,
        email=(user.email or "").lower() or None,
    )


async def _check_admin_auth(secret: str | None, request: Request, db=None) -> bool:
    """Admin auth accepting EITHER the ADMIN_TOKEN **or** an admin identity.

    ORDER IS LOAD-BEARING (Queue 386 Item 2). One ``Authorization: Bearer <x>``
    header carries two completely different credentials — the shared ADMIN_TOKEN
    that every agent lane holds, and a per-user session JWT. The token comparison
    runs FIRST and is a constant-time ``compare_digest`` against an env var: no
    database, no JWT parse, no network. A lane's request therefore takes exactly
    the path it took before this queue and never reaches the identity arm, which
    is what "lanes keep tokens, zero change to their path" means concretely.

    The identity arm runs only after the token arm has already declined, and it
    cannot alter that decline — ``_resolve_admin_user`` returns ``None`` on every
    failure rather than raising. A malformed JWT in the header is a 403, the same
    403 as a wrong token, with the same body.
    """
    # Queue 390: this is now the boolean PROJECTION of `_resolve_admin_principal`
    # rather than a second hand-copied implementation of the same two arms. The
    # ordering, the short-circuit and the indistinguishable failure all live
    # there. A privilege check duplicated is a privilege check that will
    # eventually disagree with itself about who is an admin — the same reasoning
    # that produced `_resolve_admin_user`, applied one level up.
    #
    # Queue #252 Item 4 still holds: the header form must work with no ?secret=
    # query value present.
    return await _resolve_admin_principal(secret, request, db) is not None


async def _resolve_admin_email(request: Request, db=None) -> str | None:
    """Extract the authenticated admin user's email from a Bearer token.

    Returns the email string when the request carries a valid admin Bearer
    token, or ``None`` when the caller is not authenticated or not an admin.

    Note the asymmetry with :func:`_check_admin_auth`: a request authenticated by
    the shared ADMIN_TOKEN resolves to ``None`` here, and correctly so. The token
    identifies a *capability*, not a *person* — a dozen lanes hold it. Attributing
    a gold label to "whoever had the token" would be a provenance claim the
    system cannot back up, which is worse than no claim at all.
    """
    user = await _resolve_admin_user(request, db)
    if user is None:
        return None
    return (user.email or "").lower() or None
