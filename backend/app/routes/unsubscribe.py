"""One-click email unsubscribe endpoint (CAN-SPAM compliant).

No authentication required — uses HMAC-signed tokens to identify users.
Supports both GET (one-click from email link) and POST (List-Unsubscribe-Post).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services.database import get_db_rw
from app.utils.email_compliance import (
    EMAIL_PREF_KEYS,
    get_default_email_preferences,
    verify_unsubscribe_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Email"])


def _unsubscribe_html(success: bool, message: str) -> str:
    """Render a simple HTML confirmation page."""
    status_icon = "&#10003;" if success else "&#10007;"
    status_color = "#16a34a" if success else "#dc2626"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bain Luck — Unsubscribe</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #f9fafb;
            color: #1a1a1a;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            max-width: 420px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .icon {{
            font-size: 48px;
            color: {status_color};
            margin-bottom: 16px;
        }}
        h1 {{
            font-size: 20px;
            margin: 0 0 12px;
        }}
        p {{
            font-size: 15px;
            color: #6b7280;
            line-height: 1.5;
            margin: 0 0 24px;
        }}
        a {{
            color: #2563eb;
            text-decoration: none;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">{status_icon}</div>
        <h1>{'Unsubscribed' if success else 'Something went wrong'}</h1>
        <p>{message}</p>
        <a href="https://bainluck.com">Back to Bain Luck</a>
    </div>
</body>
</html>"""


@router.get("/api/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_get(
    token: str = Query(...),
    pref: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """One-click unsubscribe via email link (GET).

    If `pref` is specified, only that email type is disabled.
    If `pref` is omitted, ALL email preferences are set to False.
    """
    return await _handle_unsubscribe(token, pref, db)


@router.post("/api/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_post(
    token: str = Query(...),
    pref: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """One-click unsubscribe via List-Unsubscribe-Post (POST).

    Same logic as GET — both are required for full email client compatibility.
    """
    return await _handle_unsubscribe(token, pref, db)


async def _handle_unsubscribe(
    token: str,
    pref: Optional[str],
    db: AsyncSession,
) -> HTMLResponse:
    """Shared unsubscribe logic for GET and POST handlers."""
    user_id = verify_unsubscribe_token(token)
    if user_id is None:
        logger.warning("Invalid unsubscribe token: %s", token[:20] if token else "empty")
        return HTMLResponse(
            content=_unsubscribe_html(
                False,
                "This unsubscribe link is invalid or expired. "
                "Please contact support if you need help.",
            ),
            status_code=400,
        )

    # Load the user to verify they exist
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("Unsubscribe token for non-existent user_id=%d", user_id)
        return HTMLResponse(
            content=_unsubscribe_html(
                False,
                "This unsubscribe link is invalid. "
                "The account may no longer exist.",
            ),
            status_code=400,
        )

    # Build the updated preferences
    current_prefs = user.email_preferences if isinstance(user.email_preferences, dict) else {}
    new_prefs = dict(current_prefs)

    if pref and pref in EMAIL_PREF_KEYS:
        # Unsubscribe from a specific email type
        new_prefs[pref] = False
        message = (
            f"You have been unsubscribed from {pref.replace('_', ' ')} emails. "
            "You can manage your other email preferences in the app."
        )
    else:
        # Unsubscribe from ALL email types
        new_prefs = get_default_email_preferences()
        message = (
            "You have been unsubscribed from all Bain Luck emails. "
            "You can re-enable notifications in the app anytime."
        )

    # Use Core update to avoid JSONB ORM assignment issues (Gotcha #4)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(email_preferences=new_prefs)
    )
    await db.commit()

    logger.info(
        "User %d unsubscribed (pref=%s, new_prefs=%s)",
        user_id, pref or "all", new_prefs,
    )

    return HTMLResponse(
        content=_unsubscribe_html(True, message),
        status_code=200,
    )
