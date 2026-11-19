"""177-A: a phone proves it owns its row without an account.

The app keeps a random secret beside its device id in the keychain. The server
stores only the secret's SHA-256; a request carries the secret in
``X-Device-Secret`` and is compared in constant time. The secret is a
credential: never logged, never echoed in an error.
"""

import hashlib
import hmac
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_device import PushDevice

SECRET_HEADER = "X-Device-Secret"
DEVICE_HEADER = "X-Device-Id"
#: The app makes 32 random bytes; base64url is 43 characters, hex is 64.
MIN_SECRET_LEN = 32
MAX_SECRET_LEN = 256


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def checked_secret(secret: Optional[str]) -> str:
    """The header's secret if it is well formed; a 401 if it is absent or not."""
    if (
        not secret
        or not MIN_SECRET_LEN <= len(secret) <= MAX_SECRET_LEN
        or any(not ("!" <= c <= "~") for c in secret)
    ):
        raise HTTPException(401, "Device secret required")
    return secret


def secret_matches(stored_hash: str, secret: str) -> bool:
    return hmac.compare_digest(stored_hash, secret_hash(secret))


def parse_device_id(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid device id") from None


async def verify_device(
    db: AsyncSession, device_id: UUID, secret: Optional[str], *, for_update: bool = False
) -> UUID:
    """The device id when the secret matches its row: 404 for no row, 403 for a
    wrong secret."""
    secret = checked_secret(secret)
    statement = select(PushDevice.secret_hash).where(PushDevice.device_id == device_id)
    if for_update:
        statement = statement.with_for_update()
    stored = (await db.execute(statement)).scalar_one_or_none()
    if stored is None:
        raise HTTPException(404, "Device not registered")
    if not secret_matches(stored, secret):
        raise HTTPException(403, "Device secret does not match")
    return device_id
