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


def is_configured() -> bool:
    """Check if Firebase Auth is configured and initialized."""
    return _init_firebase()
