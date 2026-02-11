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

    Returns None if verification fails or Firebase is not configured.
    Claims include: uid, email, name, picture, email_verified, etc.
    """
    if not _init_firebase():
        return None

    try:
        from firebase_admin import auth
        decoded = auth.verify_id_token(id_token)
        return decoded
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
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


def is_configured() -> bool:
    """Check if Firebase Auth is configured and initialized."""
    return _init_firebase()
