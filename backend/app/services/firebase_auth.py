"""
Firebase Auth initialization and token verification.

Initializes Firebase Admin SDK for verifying ID tokens from the frontend.
Auth is optional — if Firebase is not configured, all auth-dependent
endpoints return 401 and the app works in anonymous-only mode.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_firebase_initialized = False


def _init_firebase() -> bool:
    """Initialize Firebase Admin SDK. Returns True if successful."""
    global _firebase_initialized
    if _firebase_initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Option 1: Full service account JSON from env var
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase Admin SDK initialized with service account")
            return True

        # Option 2: Just the project ID (sufficient for token verification)
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if project_id:
            # Use Application Default Credentials or no credentials
            # verify_id_token only needs the project ID to check the audience claim
            firebase_admin.initialize_app(options={"projectId": project_id})
            _firebase_initialized = True
            logger.info(f"Firebase Admin SDK initialized with project ID: {project_id}")
            return True

        logger.info("Firebase not configured — auth endpoints will return 401")
        return False

    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return False


def verify_id_token(id_token: str) -> Optional[dict]:
    """
    Verify a Firebase ID token and return the decoded claims.

    Also accepts backend-issued session tokens (for Safari ITP fallback).

    Returns None if verification fails or Firebase is not configured.
    Claims include: uid, email, name, picture, email_verified, etc.
    """
    if not _init_firebase():
        return None

    # Try Firebase ID token first
    try:
        from firebase_admin import auth
        decoded = auth.verify_id_token(id_token)
        return decoded
    except Exception:
        pass  # Fall through to session token check

    # Try backend-issued session token (Safari ITP fallback)
    session_claims = verify_session_token(id_token)
    if session_claims:
        logger.debug(f"Verified backend session token for uid={session_claims.get('uid')}")
        return session_claims

    logger.warning("Token verification failed: neither Firebase ID token nor backend session token")
    return None


def get_or_create_firebase_user(email: str, display_name: Optional[str] = None, photo_url: Optional[str] = None) -> Optional[str]:
    """
    Look up a Firebase user by email, or create one if not found.
    Returns the Firebase UID, or None if Firebase is not configured.
    """
    if not _init_firebase():
        return None

    try:
        from firebase_admin import auth

        try:
            user_record = auth.get_user_by_email(email)
            return user_record.uid
        except auth.UserNotFoundError:
            user_record = auth.create_user(
                email=email,
                display_name=display_name,
                photo_url=photo_url,
            )
            logger.info(f"Created Firebase user: {user_record.uid}")
            return user_record.uid
    except Exception as e:
        logger.warning(f"Failed to get/create Firebase user: {e}")
        return None


def create_custom_token(uid: str) -> Optional[str]:
    """
    Create a Firebase custom token for the given UID.
    Requires Firebase Admin SDK initialized with a service account.
    Returns None if not available.
    """
    if not _init_firebase():
        return None

    try:
        from firebase_admin import auth

        custom_token = auth.create_custom_token(uid)
        # create_custom_token returns bytes in some SDK versions
        if isinstance(custom_token, bytes):
            return custom_token.decode("utf-8")
        return custom_token
    except Exception as e:
        logger.warning(f"Failed to create custom token: {e}")
        return None


def create_session_token(uid: str, email: Optional[str] = None,
                         name: Optional[str] = None,
                         picture: Optional[str] = None,
                         ttl_seconds: int = 28800) -> Optional[str]:
    """
    Create a backend-signed session token for Safari ITP fallback.

    When Safari blocks identitytoolkit.googleapis.com entirely, neither
    signInWithCredential nor signInWithCustomToken works. This token
    serves as a direct-use Bearer token that our verify_id_token() can
    validate alongside normal Firebase ID tokens.

    Uses PyJWT with HS256 signed by a hash of the service account key.
    """
    import hashlib
    import time

    signing_key = _get_session_signing_key()
    if not signing_key:
        return None

    try:
        import jwt  # PyJWT

        now = int(time.time())
        payload = {
            "uid": uid,
            "email": email,
            "name": name,
            "picture": picture,
            "iss": "bainluck-backend",
            "iat": now,
            "exp": now + ttl_seconds,
        }
        return jwt.encode(payload, signing_key, algorithm="HS256")
    except Exception as e:
        logger.warning(f"Failed to create session token: {e}")
        return None


def verify_session_token(token: str) -> Optional[dict]:
    """
    Verify a backend-issued session token.
    Returns claims dict (uid, email, name, picture) or None.
    """
    signing_key = _get_session_signing_key()
    if not signing_key:
        return None

    try:
        import jwt  # PyJWT

        payload = jwt.decode(token, signing_key, algorithms=["HS256"],
                             options={"require": ["uid", "exp", "iss"]})
        if payload.get("iss") != "bainluck-backend":
            return None
        return payload
    except Exception:
        return None


def _get_session_signing_key() -> Optional[str]:
    """
    Derive a signing key for session tokens.
    Uses ADMIN_SECRET if available, otherwise derives from service account.
    """
    import hashlib

    # Prefer ADMIN_SECRET (simple, already exists)
    admin_secret = os.getenv("ADMIN_SECRET")
    if admin_secret:
        return hashlib.sha256(f"bainluck-session:{admin_secret}".encode()).hexdigest()

    # Fallback: derive from service account JSON
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        return hashlib.sha256(f"bainluck-session:{sa_json[:64]}".encode()).hexdigest()

    return None


def is_configured() -> bool:
    """Check if Firebase Auth is configured and initialized."""
    return _init_firebase()
