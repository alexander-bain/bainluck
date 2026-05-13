"""Push notification device token registration."""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class DeviceTokenRegistration(BaseModel):
    device_token: str
    platform: str  # "ios" or "macos"
    session_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/register")
async def register_device_token(
    body: DeviceTokenRegistration,
    request: Request,
):
    """Register a device token for push notifications.

    For now, just logs the token. A device_tokens table will be added
    later when we build the full notification pipeline.
    """
    # Prefer session_id from header (matches other endpoints)
    session_id = body.session_id or request.headers.get("x-session-id")

    logger.info(
        "Device token registered: platform=%s session=%s user=%s token=%s...%s",
        body.platform,
        session_id,
        body.user_id,
        body.device_token[:8] if len(body.device_token) >= 8 else body.device_token,
        body.device_token[-4:] if len(body.device_token) >= 4 else "",
    )

    return {"status": "ok"}
