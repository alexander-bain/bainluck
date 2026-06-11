"""Push notification device token registration and test sending."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DeviceToken
from app.routes.admin_utils import _check_admin_secret
from app.services.database import get_db, get_db_rw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class DeviceTokenRegistration(BaseModel):
    device_token: str
    platform: str  # "ios" or "macos"
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class TestNotificationRequest(BaseModel):
    device_token: str
    title: Optional[str] = "Bain Luck"
    body: Optional[str] = "Test notification from Bain Luck"


@router.post("/register")
async def register_device_token(
    request: Request,
    body: DeviceTokenRegistration,
    db: AsyncSession = Depends(get_db_rw),
):
    """Register a device token for push notifications.

    Upserts the token: if the same device_token already exists, updates
    the user/session/platform and marks it active.
    """
    session_id = body.session_id or request.headers.get("x-session-id")

    # Parse user_id to int if provided
    user_id_int: Optional[int] = None
    if body.user_id:
        try:
            user_id_int = int(body.user_id)
        except (ValueError, TypeError):
            pass

    logger.info(
        "Device token registration: platform=%s session=%s user=%s token=%s...%s",
        body.platform,
        session_id,
        body.user_id,
        body.device_token[:8] if len(body.device_token) >= 8 else body.device_token,
        body.device_token[-4:] if len(body.device_token) >= 4 else "",
    )

    # Upsert: insert or update on conflict
    stmt = pg_insert(DeviceToken).values(
        device_token=body.device_token,
        platform=body.platform,
        user_id=user_id_int,
        session_id=session_id,
        is_active=True,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_device_tokens_token",
        set_={
            "platform": body.platform,
            "user_id": user_id_int,
            "session_id": session_id,
            "is_active": True,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()

    return {"status": "ok"}


@router.post("/admin/send-test")
async def send_test_notification(
    request: Request,
    body: TestNotificationRequest,
    secret: str = Query(None),
):
    """Send a test push notification to a specific device token.

    Requires admin secret. Uses Firebase Cloud Messaging (FCM) to send
    via APNS. The device_token must be an FCM registration token.

    NOTE: The iOS app currently captures raw APNS tokens. FCM's
    messaging.send() requires FCM registration tokens, not raw APNS
    tokens. To make this work, the iOS app needs to add
    FirebaseMessaging SDK and use Messaging.messaging().fcmToken
    instead of the raw APNS device token.
    """
    _check_admin_secret(secret, request=request)

    try:
        from firebase_admin import messaging

        from app.services.firebase_auth import _init_firebase

        if not _init_firebase():
            raise HTTPException(
                status_code=500, detail="Firebase Admin SDK not configured"
            )

        # Build an FCM message
        message = messaging.Message(
            notification=messaging.Notification(
                title=body.title,
                body=body.body,
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=body.title,
                            body=body.body,
                        ),
                        sound="default",
                        badge=1,
                    ),
                ),
            ),
            token=body.device_token,
        )

        response = messaging.send(message)
        logger.info("Test notification sent: %s", response)

        return {"status": "sent", "message_id": response}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to send test notification: %s", e)
        error_msg = str(e)
        hint = None
        if "not a valid FCM registration token" in error_msg.lower() or "invalid registration" in error_msg.lower():
            hint = (
                "The token is a raw APNS token, not an FCM registration token. "
                "Add FirebaseMessaging SDK to the iOS app and use "
                "Messaging.messaging().fcmToken instead."
            )
        return {
            "status": "error",
            "error": error_msg,
            "hint": hint,
        }


@router.get("/admin/tokens")
async def list_device_tokens(
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all registered device tokens. Requires admin secret."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(
        select(DeviceToken)
        .where(DeviceToken.is_active.is_(True))
        .order_by(DeviceToken.updated_at.desc())
        .limit(50)
    )
    tokens = result.scalars().all()

    return {
        "count": len(tokens),
        "tokens": [
            {
                "id": t.id,
                "platform": t.platform,
                "user_id": t.user_id,
                "session_id": t.session_id,
                "token_prefix": t.device_token[:8],
                "token_suffix": t.device_token[-4:],
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tokens
        ],
    }
