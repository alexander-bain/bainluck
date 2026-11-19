"""177-A / 178-B: a phone registers its pins and push tokens without an account.

``PUT /api/devices/{device_id}`` replaces the phone's whole state; the app sends
it on every launch and on any token or pin change. The first PUT for an id sets
its secret, and every later request must carry the same one (``X-Device-Secret``).

Tokens are transport credentials: no response carries one (only whether it is
on file), no log line names one, and a malformed body gets a generic 422 that
never echoes its input. Requests are bounded by the app-wide per-IP limit in
``RateLimitMiddleware``.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.device_auth import (
    SECRET_HEADER,
    checked_secret,
    parse_device_id,
    secret_hash,
    secret_matches,
    verify_device,
)
from app.models.models import User, UserPin
from app.models.push_device import APNS_ENVS, MAX_PINS_PER_KIND, PLATFORMS, PushDevice
from app.services.database import get_db_rw

router = APIRouter(prefix="/api/devices", tags=["devices"])
_TABLE = PushDevice.__table__
#: The signed-in pin cap (`routes/user.py`); a claim merges up to this many.
_ACCOUNT_PINS_PER_TYPE = 25
_MAX_BODY = 8192


def _hex_token(token: Optional[SecretStr]) -> Optional[SecretStr]:
    if token is None:
        return None
    value = token.get_secret_value()
    if (
        not 2 <= len(value) <= 1024
        or len(value) % 2
        or any(c not in "0123456789abcdefABCDEF" for c in value)
    ):
        raise ValueError("Invalid push token")
    return SecretStr(value.lower())


class DeviceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str
    apns_env: str
    notification_token: Optional[SecretStr] = Field(default=None, repr=False)
    la_start_token: Optional[SecretStr] = Field(default=None, repr=False)
    os_major: Optional[int] = Field(default=None, strict=True, ge=0, le=99)
    app_version: Optional[str] = Field(default=None, max_length=20)
    pinned_event_ids: list[int] = Field(default_factory=list, max_length=MAX_PINS_PER_KIND)
    pinned_market_ids: list[int] = Field(default_factory=list, max_length=MAX_PINS_PER_KIND)

    @field_validator("platform")
    @classmethod
    def _platform(cls, value: str) -> str:
        if value not in PLATFORMS:
            raise ValueError("Unknown platform")
        return value

    @field_validator("apns_env")
    @classmethod
    def _env(cls, value: str) -> str:
        if value not in APNS_ENVS:
            raise ValueError("Unknown push environment")
        return value

    @field_validator("notification_token", "la_start_token")
    @classmethod
    def _tokens(cls, value: Optional[SecretStr]) -> Optional[SecretStr]:
        return _hex_token(value)

    @field_validator("pinned_event_ids", "pinned_market_ids")
    @classmethod
    def _ids(cls, value: list[int]) -> list[int]:
        if any(isinstance(i, bool) or not 0 < i < 2**31 for i in value):
            raise ValueError("Invalid pin id")
        return sorted(set(value))


async def _state(request: Request) -> DeviceState:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > _MAX_BODY:
            raise HTTPException(413, "Device body too large")
    try:
        state = DeviceState.model_validate_json(body)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid device request") from None
    if state.platform == "appclip" and state.la_start_token is not None:
        # The App Clip shows no Live Activities (176-A).
        raise HTTPException(422, "Invalid device request")
    return state


def _public(row) -> dict:
    return {
        "device_id": str(row["device_id"]),
        "platform": row["platform"],
        "pinned_event_ids": list(row["pinned_event_ids"] or []),
        "pinned_market_ids": list(row["pinned_market_ids"] or []),
        "notification_token_on_file": row["notification_token"] is not None,
        "la_start_token_on_file": row["la_start_token"] is not None,
        "signed_in": row["user_id"] is not None,
    }


async def _row(db: AsyncSession, device_id: UUID):
    result = await db.execute(select(_TABLE).where(_TABLE.c.device_id == device_id))
    return result.mappings().one()


@router.put("/{device_id}")
async def put_device(
    device_id: str,
    request: Request,
    x_device_secret: Optional[str] = Header(default=None, alias=SECRET_HEADER),
    db: AsyncSession = Depends(get_db_rw),
):
    """Replace the phone's whole state; the first call sets its secret."""
    device = parse_device_id(device_id)
    secret = checked_secret(x_device_secret)
    state = await _state(request)
    notification = state.notification_token.get_secret_value() if state.notification_token else None
    la_start = state.la_start_token.get_secret_value() if state.la_start_token else None
    values = {
        "platform": state.platform,
        "apns_env": state.apns_env,
        "notification_token": notification,
        "la_start_token": la_start,
        "os_major": state.os_major,
        "app_version": state.app_version,
        "pinned_event_ids": state.pinned_event_ids,
        "pinned_market_ids": state.pinned_market_ids,
    }
    try:
        # The row is created WITHOUT its tokens: a token still held by an old row
        # would fail the unique check before the move below could free it, and
        # nothing is moved until the secret has been checked.
        untokened = {**values, "notification_token": None, "la_start_token": None}
        await db.execute(
            insert(_TABLE)
            .values(device_id=device, secret_hash=secret_hash(secret), **untokened)
            .on_conflict_do_nothing(index_elements=[_TABLE.c.device_id])
        )
        stored = (
            await db.execute(
                select(_TABLE.c.secret_hash, _TABLE.c.la_start_token)
                .where(_TABLE.c.device_id == device)
                .with_for_update()
            )
        ).one()
        if not secret_matches(stored.secret_hash, secret):
            await db.rollback()
            raise HTTPException(403, "Device secret does not match")
        # A token that reappears under a new id (a reinstall or a restore) moves:
        # the old row stops holding it, so one phone is never pushed twice.
        for column, token in (("notification_token", notification), ("la_start_token", la_start)):
            if token is not None:
                await db.execute(
                    update(_TABLE)
                    .where(_TABLE.c[column] == token, _TABLE.c.device_id != device)
                    .values({column: None})
                )
        stamps = {"updated_at": func.now(), "last_seen_at": func.now()}
        if la_start is not None and la_start != stored.la_start_token:
            stamps["la_start_token_at"] = func.now()
        elif la_start is None:
            stamps["la_start_token_at"] = None
        await db.execute(
            update(_TABLE).where(_TABLE.c.device_id == device).values(**values, **stamps)
        )
        row = await _row(db, device)
        public = _public(row)
        await db.commit()
        return public
    except IntegrityError:
        await db.rollback()
        # SQL errors carry bound tokens: never log, chain or expose them.
        raise HTTPException(409, "Device conflict") from None
    except DBAPIError:
        await db.rollback()
        raise HTTPException(503, "Device registration temporarily unavailable") from None


@router.get("/{device_id}")
async def get_device(
    device_id: str,
    x_device_secret: Optional[str] = Header(default=None, alias=SECRET_HEADER),
    db: AsyncSession = Depends(get_db_rw),
):
    """The phone's pins, and whether each token is on file (never the token)."""
    device = await verify_device(db, parse_device_id(device_id), x_device_secret)
    return _public(await _row(db, device))


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    x_device_secret: Optional[str] = Header(default=None, alias=SECRET_HEADER),
    db: AsyncSession = Depends(get_db_rw),
):
    """Forget the phone: its row goes, and its Live Activity registrations with it."""
    device = await verify_device(
        db, parse_device_id(device_id), x_device_secret, for_update=True
    )
    await db.execute(delete(_TABLE).where(_TABLE.c.device_id == device))
    await db.commit()
    return Response(status_code=204)


@router.post("/{device_id}/claim")
async def claim_device(
    device_id: str,
    x_device_secret: Optional[str] = Header(default=None, alias=SECRET_HEADER),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_rw),
):
    """Signed in: the phone joins the account and its pins follow the reader."""
    device = await verify_device(
        db, parse_device_id(device_id), x_device_secret, for_update=True
    )
    await db.execute(
        update(_TABLE)
        .where(_TABLE.c.device_id == device)
        .values(user_id=user.id, updated_at=func.now())
    )
    row = await _row(db, device)
    existing = (
        await db.execute(
            select(UserPin.pin_type, UserPin.target_id).where(UserPin.user_id == user.id)
        )
    ).all()
    have = {(p.pin_type, p.target_id) for p in existing}
    for pin_type, ids in (("event", row["pinned_event_ids"]), ("future", row["pinned_market_ids"])):
        room = _ACCOUNT_PINS_PER_TYPE - sum(1 for t, _ in have if t == pin_type)
        for target in ids or []:
            if room <= 0:
                break
            if (pin_type, target) in have:
                continue
            await db.execute(
                insert(UserPin.__table__)
                .values(user_id=user.id, pin_type=pin_type, target_id=target)
                .on_conflict_do_nothing(constraint="uq_user_pin")
            )
            have.add((pin_type, target))
            room -= 1
    public = _public(row)
    await db.commit()
    return public
