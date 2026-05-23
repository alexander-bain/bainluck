"""CAN-SPAM email compliance utilities.

Provides:
- HMAC-signed unsubscribe token generation and verification
- List-Unsubscribe / List-Unsubscribe-Post header generation
- Email preference constants and helpers

All outgoing emails MUST include List-Unsubscribe headers (required by
Gmail and Yahoo for bulk senders). Use `generate_unsubscribe_headers()`
to add them to any EmailMessage or MIME message before sending.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

# Preference keys — add new types here when new email categories are introduced.
# All default to False (opt-in required).
EMAIL_PREF_KEYS = frozenset({"digest", "bug_updates", "market_alerts"})

# Base URL for unsubscribe links
_API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.bainluck.com")

# Secret key for HMAC token signing — falls back to ADMIN_TOKEN if not set.
# In production, set EMAIL_HMAC_SECRET to a dedicated secret.
_HMAC_SECRET = os.environ.get("EMAIL_HMAC_SECRET") or os.environ.get("ADMIN_TOKEN", "")


def _get_hmac_secret() -> str:
    """Return the HMAC secret, reading from env at call time for testability."""
    return (
        os.environ.get("EMAIL_HMAC_SECRET")
        or os.environ.get("ADMIN_TOKEN", "")
    )


def generate_unsubscribe_token(user_id: int) -> str:
    """Generate an HMAC-signed unsubscribe token for a user.

    The token encodes the user_id so we can look up the user from the token
    without a database query on the hot path (the HMAC prevents forgery).

    Format: {user_id}:{hmac_hex}
    """
    secret = _get_hmac_secret()
    if not secret:
        raise ValueError(
            "EMAIL_HMAC_SECRET or ADMIN_TOKEN must be set to generate "
            "unsubscribe tokens"
        )
    payload = str(user_id)
    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{user_id}:{sig}"


def verify_unsubscribe_token(token: str) -> Optional[int]:
    """Verify an unsubscribe token and return the user_id, or None if invalid.

    Performs constant-time comparison to prevent timing attacks.
    """
    if not token or ":" not in token:
        return None

    parts = token.split(":", 1)
    if len(parts) != 2:
        return None

    try:
        user_id = int(parts[0])
    except (ValueError, TypeError):
        return None

    expected = generate_unsubscribe_token(user_id)
    if hmac.compare_digest(token, expected):
        return user_id
    return None


def get_default_email_preferences() -> dict:
    """Return the default email preferences (all opted out)."""
    return {key: False for key in sorted(EMAIL_PREF_KEYS)}


def merge_email_preferences(
    existing: Optional[dict], updates: dict
) -> dict:
    """Merge email preference updates into existing preferences.

    Only allows known keys. Unknown keys in updates are silently ignored.
    Values must be booleans.
    """
    result = dict(existing) if existing else get_default_email_preferences()
    for key in EMAIL_PREF_KEYS:
        if key in updates and isinstance(updates[key], bool):
            result[key] = updates[key]
    return result


def generate_unsubscribe_url(
    unsubscribe_token: str,
    pref: Optional[str] = None,
) -> str:
    """Build a one-click unsubscribe URL.

    Args:
        unsubscribe_token: The user's HMAC-signed token.
        pref: Optional specific preference to unsubscribe from.
              If None, unsubscribes from all email types.
    """
    base = f"{_API_BASE_URL}/api/unsubscribe?token={unsubscribe_token}"
    if pref and pref in EMAIL_PREF_KEYS:
        base += f"&pref={pref}"
    return base


def generate_unsubscribe_headers(
    unsubscribe_token: str,
    pref: Optional[str] = None,
) -> dict[str, str]:
    """Generate List-Unsubscribe and List-Unsubscribe-Post headers.

    These headers are REQUIRED by Gmail and Yahoo for bulk email senders.
    Add them to every outgoing email.

    Returns a dict of header name -> value pairs to set on the email message.

    Usage:
        headers = generate_unsubscribe_headers(user.unsubscribe_token, "digest")
        for header_name, header_value in headers.items():
            message[header_name] = header_value
    """
    url = generate_unsubscribe_url(unsubscribe_token, pref)
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
