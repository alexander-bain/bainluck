"""
Authentication routes.

Handles Firebase ID token verification, user creation/lookup,
and profile management.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_current_user
from app.models.models import User, UserPreference
from app.services.database import get_db, get_db_rw
from app.services.firebase_auth import verify_id_token, is_configured, get_or_create_firebase_user, create_custom_token, verify_apple_id_token

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Request/Response schemas ---

class GoogleAuthRequest(BaseModel):
    """Request body for Google sign-in."""
    id_token: str


class GoogleAccessTokenRequest(BaseModel):
    """Request body for Google access token exchange."""
    access_token: str


class AppleAuthRequest(BaseModel):
    """Request body for Apple Sign-In."""
    id_token: str              # Apple-issued JWT
    first_name: Optional[str] = None  # Only sent on first authorization
    last_name: Optional[str] = None   # Only sent on first authorization


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


# --- Google access-token audience validation (Queue 282 / C78) ---
#
# The confused-deputy fix. Google's userinfo endpoint accepts an access token
# minted for ANY Google OAuth client, so verifying a token with userinfo alone
# lets a token issued to a third party's app mint a Bain Luck session. Before any
# Firebase/DB/token side effect we introspect the token server-side (tokeninfo,
# which — unlike userinfo — returns the client binding aud/azp) and require the
# audience to belong to one of our own OAuth clients.
#
# Preferred source of truth is the server-owned GOOGLE_OAUTH_CLIENT_IDS allowlist
# (comma-separated web + iOS client IDs). When that is unset we fall back to a
# deploy-safe default: accept only client IDs from our own Google Cloud project
# (the project-number prefix below, sourced from the committed
# ios/.../GoogleService-Info.plist CLIENT_ID). That still rejects every
# cross-project (confused-deputy) token while keeping sign-in working before the
# allowlist is configured. A request-supplied client ID is NEVER trusted.
_GOOGLE_PROJECT_CLIENT_PREFIX = "899260594814-"
_GOOGLE_CLIENT_ID_SUFFIX = ".apps.googleusercontent.com"
_GOOGLE_HTTP_TIMEOUT = 8.0  # seconds; bounds each Google introspection call


def _google_oauth_client_allowlist() -> set[str]:
    """Server-owned set of accepted Google OAuth client IDs (may be empty)."""
    raw = os.getenv("GOOGLE_OAUTH_CLIENT_IDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _google_client_id_trusted(client_id: Optional[str]) -> bool:
    """True only when ``client_id`` is one of our own OAuth clients.

    Uses the explicit allowlist when configured; otherwise falls back to the
    same-project prefix default. Never accepts a missing/empty client id.
    """
    if not client_id or not isinstance(client_id, str):
        return False
    allowlist = _google_oauth_client_allowlist()
    if allowlist:
        return client_id in allowlist
    return client_id.startswith(_GOOGLE_PROJECT_CLIENT_PREFIX) and client_id.endswith(
        _GOOGLE_CLIENT_ID_SUFFIX
    )


def _google_audience_ok(aud: Optional[str], azp: Optional[str]) -> bool:
    """Validate the introspected client binding.

    The token's audience (``aud``) must be one of our clients, and when the
    authorized party (``azp``) is present it must be one of ours too — an
    ``azp`` naming a different client is a mismatch even if ``aud`` is ours.
    """
    if not _google_client_id_trusted(aud):
        return False
    if azp and not _google_client_id_trusted(azp):
        return False
    return True


def _google_email_verified(userinfo: dict) -> bool:
    """Whether Google reports the profile email as verified.

    v3 userinfo returns ``email_verified`` as a bool; tolerate the string form.
    """
    val = userinfo.get("email_verified")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"1", "true", "yes"}
    return False


# --- Endpoints ---

class EmailSignInRequest(BaseModel):
    """Request body for direct email sign-in (admin only)."""
    email: str


def _email_sign_in_enabled() -> bool:
    """Whether the passwordless email sign-in path is enabled.

    SECURITY (Queue #252 Item 1): this endpoint mints a full session token from
    an email address ALONE — no credential, no proof of identity. That is a live
    admin-takeover path: anyone who knows an allowlisted admin email becomes that
    admin. It is therefore DISABLED by default and must be explicitly opted into
    for local/dev convenience via ENABLE_INSECURE_EMAIL_SIGN_IN=1. In production
    the flag is unset, so the endpoint always returns 401. Real admins sign in via
    the verified Google/Apple OAuth flows (/api/auth/google, /api/auth/apple).
    """
    return os.getenv("ENABLE_INSECURE_EMAIL_SIGN_IN", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


@router.post("/email-sign-in")
async def email_sign_in(
    body: EmailSignInRequest,
    db: AsyncSession = Depends(get_db_rw),
):
    """Direct sign-in for admin emails — DISABLED by default (dev-only).

    See ``_email_sign_in_enabled``. Email-in-body alone is never sufficient to
    mint a token; without the explicit non-production opt-in flag this returns
    401. When enabled for dev, it still requires the email to be allowlisted.
    """
    from app.routes.admin_utils import _admin_user_emails

    if not _email_sign_in_enabled():
        logger.warning("Rejected disabled email-sign-in attempt for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Direct email sign-in is disabled. Sign in with Google or Apple.",
        )

    email = body.email.strip().lower()
    if email not in _admin_user_emails():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not authorized for direct sign-in",
        )

    firebase_uid = get_or_create_firebase_user(email, None, None)
    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase not configured",
        )

    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(firebase_uid=firebase_uid, email=email)
        db.add(user)
        await db.flush()
        await db.refresh(user)
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        user.preferences = prefs

    onboarding_completed = bool(user.preferences and user.preferences.onboarding_completed)

    from app.services.firebase_auth import create_session_token
    session_token = create_session_token(uid=firebase_uid, email=email)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session token",
        )

    logger.info(f"Email sign-in: email={email}, uid={firebase_uid}")

    return {
        "id_token": session_token,
        "uid": firebase_uid,
        "email": email,
        "name": None,
        "picture": None,
        "expires_in": 2592000,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "photo_url": user.photo_url,
            "onboarding_completed": onboarding_completed,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


@router.get("/status")
async def auth_status():
    """Check if authentication is configured."""
    providers = []
    if is_configured():
        providers.append("google")
    if os.getenv("APPLE_SERVICES_ID"):
        providers.append("apple")
    return {
        "auth_configured": is_configured(),
        "providers": providers,
    }


@router.get("/health")
async def auth_health():
    """Deep health check: verify Firebase SDK can actually create tokens."""
    from app.services.firebase_auth import _init_firebase, create_custom_token

    checks = {
        "firebase_init": False,
        "custom_token": False,
        "apple_configured": bool(os.getenv("APPLE_SERVICES_ID")),
        "apple_bundle_id": os.getenv("APPLE_BUNDLE_ID", "com.bainluck.Bain-Luck"),
    }

    try:
        checks["firebase_init"] = _init_firebase()
    except Exception as e:
        checks["firebase_init_error"] = str(e)

    if checks["firebase_init"]:
        token = create_custom_token("healthcheck-test-uid")
        checks["custom_token"] = token is not None
        if not token:
            checks["custom_token_error"] = "create_custom_token returned None"

    checks["healthy"] = checks["firebase_init"] and checks["custom_token"]
    return checks


@router.post("/google", response_model=UserProfileResponse)
async def google_sign_in(
    body: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Verify a Firebase ID token from Google Sign-In and return the user profile.
    Creates a new user if this is the first sign-in.

    SECURITY (Queue #255 Item 1): ``allow_session_token=False`` so ONLY a genuine
    Firebase ID token reaches this create path. A backend-issued session token
    (Safari ITP fallback) must never mint/resurrect a User here — otherwise an old
    token from a since-deleted account could re-create it on the next sign-in.
    """
    claims = verify_id_token(body.id_token, allow_session_token=False)
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
        await db.refresh(user)  # Load server_default values (created_at)

        # Create empty preferences
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        user.preferences = prefs

    onboarding_completed = bool(user.preferences and user.preferences.onboarding_completed)

    logger.info(f"User signed in: uid={firebase_uid}, email={email}")

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        onboarding_completed=onboarding_completed,
        created_at=user.created_at.isoformat(),
    )


@router.post("/google-access-token")
async def google_access_token_sign_in(
    body: GoogleAccessTokenRequest,
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Exchange a Google access token for a Firebase custom token.

    This is a fallback for browsers where signInWithCredential fails
    (e.g., Safari with ITP blocking Identity Platform requests).

    Flow: verify access token with Google → get/create Firebase user →
    create custom token → frontend calls signInWithCustomToken.
    """
    import httpx

    access_token = body.access_token

    # === Step 1: introspect the access token audience BEFORE any side effect ===
    # (Queue 282 / C78 confused-deputy fix). tokeninfo returns the client binding
    # (aud/azp); userinfo does not. Reject a token that was not minted for one of
    # our own OAuth clients before touching Firebase, the database, or any token
    # mint. Never log the raw token or the introspection payload.
    try:
        async with httpx.AsyncClient(timeout=_GOOGLE_HTTP_TIMEOUT) as client:
            tok_resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": access_token},
            )
    except httpx.HTTPError:
        # Transport failure reaching Google — retryable, no side effect taken.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify Google token",
        )

    if tok_resp.status_code != 200:
        # Non-2xx from tokeninfo means the token is invalid/expired/revoked.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google access token",
        )

    try:
        tokeninfo = tok_resp.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google access token",
        )

    if not isinstance(tokeninfo, dict) or tokeninfo.get("error") or tokeninfo.get(
        "error_description"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google access token",
        )

    if not _google_audience_ok(tokeninfo.get("aud"), tokeninfo.get("azp")):
        # Do not leak the offending client id — just refuse the confused deputy.
        logger.warning(
            "Google access-token rejected: audience not in server allowlist"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token audience not recognized",
        )

    # === Step 2: fetch the profile and require a verified email ===
    try:
        async with httpx.AsyncClient(timeout=_GOOGLE_HTTP_TIMEOUT) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify Google token",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google access token",
        )

    try:
        userinfo = resp.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google access token",
        )
    if not isinstance(userinfo, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google access token",
        )

    email = userinfo.get("email")
    name = userinfo.get("name")
    picture = userinfo.get("picture")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token missing email",
        )

    # Email is account identity here — only trust Google's verified signal.
    if not _google_email_verified(userinfo):
        logger.warning("Google access-token rejected: email not verified")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google email not verified",
        )

    # Get or create Firebase user (uses email lookup to match existing accounts)
    firebase_uid = get_or_create_firebase_user(email, name, picture)
    if not firebase_uid:
        logger.error("Google auth: get_or_create_firebase_user returned None for email=%s", email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase not configured or user creation failed",
        )

    # Create custom token for frontend signInWithCustomToken
    custom_token = create_custom_token(firebase_uid)
    if not custom_token:
        logger.error("Google auth: create_custom_token returned None for uid=%s", firebase_uid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create custom token (service account may not be configured)",
        )

    # Upsert user in our database
    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    if user:
        if email:
            user.email = email
        if name and not user.display_name:
            user.display_name = name
        if picture:
            user.photo_url = picture
    else:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            display_name=name,
            photo_url=picture,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)  # Load server_default values (created_at)

        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        user.preferences = prefs

    onboarding_completed = bool(user.preferences and user.preferences.onboarding_completed)

    logger.info(f"Access token exchange: uid={firebase_uid}, email={email}, new_user={user.id is not None}")

    # Also create a backend session token for Safari ITP fallback.
    # When signInWithCustomToken also fails (because Safari blocks
    # identitytoolkit.googleapis.com entirely), the frontend needs a token
    # it can use directly for API calls without going through Firebase client SDK.
    from app.services.firebase_auth import create_session_token
    fallback_id_token = create_session_token(
        uid=firebase_uid, email=email, name=name, picture=picture
    )
    if not fallback_id_token:
        logger.error("Google auth: create_session_token returned None for uid=%s", firebase_uid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session token",
        )

    return {
        "custom_token": custom_token,
        "id_token": fallback_id_token,
        "uid": firebase_uid,
        "email": email,
        "name": name,
        "picture": picture,
        "expires_in": 2592000,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "photo_url": user.photo_url,
            "onboarding_completed": onboarding_completed,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


@router.post("/apple")
async def apple_sign_in(
    body: AppleAuthRequest,
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Verify an Apple id_token and exchange for Firebase credentials.

    Flow: Apple JS SDK popup → id_token → verify against Apple JWKS →
    get/create Firebase user → create custom token + session token.

    Apple only sends the user's name on the FIRST authorization. After that,
    only `sub` and `email` are in the JWT. The frontend must pass
    first_name/last_name from the initial response.
    """
    apple_services_id = os.getenv("APPLE_SERVICES_ID")
    if not apple_services_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Apple Sign-In not configured",
        )

    # Accept both web Services ID and iOS bundle ID as valid audiences
    apple_bundle_id = os.getenv("APPLE_BUNDLE_ID", "com.bainluck.Bain-Luck")
    valid_audiences = [apple_services_id, apple_bundle_id]

    # Verify the Apple id_token JWT
    logger.info("Apple auth: verifying id_token with audiences=%s", valid_audiences)
    claims = verify_apple_id_token(body.id_token, valid_audiences)
    if not claims:
        logger.warning("Apple auth: id_token verification failed for audiences=%s", valid_audiences)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Apple id_token",
        )

    email = claims.get("email")
    apple_sub = claims.get("sub")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apple token missing email claim",
        )

    # Build display name from first auth data (only available once)
    display_name = None
    if body.first_name or body.last_name:
        parts = [p for p in [body.first_name, body.last_name] if p]
        display_name = " ".join(parts) if parts else None

    # Get or create Firebase user (uses email lookup to match existing accounts)
    logger.info("Apple auth: getting/creating Firebase user for email=%s", email)
    firebase_uid = get_or_create_firebase_user(email, display_name, None)
    if not firebase_uid:
        logger.error("Apple auth: get_or_create_firebase_user returned None for email=%s", email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase not configured or user creation failed",
        )

    # Create custom token for frontend signInWithCustomToken
    custom_token = create_custom_token(firebase_uid)
    if not custom_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create custom token (service account may not be configured)",
        )

    # Upsert user in our database
    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    if user:
        if email:
            user.email = email
        if display_name and not user.display_name:
            user.display_name = display_name
    else:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
            photo_url=None,  # Apple doesn't provide profile photos
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)  # Load server_default values (created_at)

        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        user.preferences = prefs

    onboarding_completed = bool(user.preferences and user.preferences.onboarding_completed)

    is_new = user.id is not None  # always true after flush, but log for tracing
    logger.info(f"Apple sign-in: uid={firebase_uid}, email={email}, apple_sub={apple_sub}, new_user={is_new}")

    # Create backend session token for Safari ITP fallback
    from app.services.firebase_auth import create_session_token
    fallback_id_token = create_session_token(
        uid=firebase_uid, email=email, name=display_name, picture=None
    )
    if not fallback_id_token:
        logger.error("Apple auth: create_session_token returned None for uid=%s", firebase_uid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session token",
        )

    return {
        "custom_token": custom_token,
        "id_token": fallback_id_token,
        "uid": firebase_uid,
        "email": email,
        "name": display_name,
        "picture": None,
        "expires_in": 2592000,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "photo_url": user.photo_url,
            "onboarding_completed": onboarding_completed,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


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

    onboarding_completed = bool(user.preferences and user.preferences.onboarding_completed)

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
    db: AsyncSession = Depends(get_db_rw),
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

    onboarding_completed = bool(user.preferences and user.preferences.onboarding_completed)

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
    db: AsyncSession = Depends(get_db_rw),
):
    """Delete the current user's account and all associated data."""
    await db.delete(user)
    logger.info(f"User account deleted: id={user.id}")
    return {"status": "deleted"}
