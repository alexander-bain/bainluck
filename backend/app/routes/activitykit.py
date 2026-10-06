"""Signed-in ActivityKit ownership/CAS; no token acquisition or APNs delivery."""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.models.activitykit import ActivityKitRegistration
from app.models.models import Event, User
from app.services.database import get_db_rw

router = APIRouter(prefix="/api/activitykit/registrations", tags=["activitykit"])
_TABLE = ActivityKitRegistration.__table__


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int = Field(strict=True, gt=0, le=(1 << 63) - 1)
    expected_version: int = Field(strict=True, ge=0, le=(1 << 63) - 2)
    mutation_id: UUID


class Registration(Mutation):
    push_token: SecretStr = Field(repr=False)

    @field_validator("push_token")
    @classmethod
    def validate_token(cls, token: SecretStr) -> SecretStr:
        value = token.get_secret_value()
        if (
            not 2 <= len(value) <= 1024
            or len(value) % 2
            or any(c not in "0123456789abcdefABCDEF" for c in value)
        ):
            raise ValueError("Invalid ActivityKit token")
        return SecretStr(value.lower())


def _activity_id(value: str) -> str:
    if not 1 <= len(value) <= 128 or any(
        not (c.isascii() and (c.isalnum() or c in "-_")) for c in value
    ):
        raise HTTPException(422, "Invalid activity identity")
    return value


async def _body(request: Request, model: type[Mutation]) -> Mutation:
    # Auth dependency is resolved before reading a body. Manual validation avoids
    # FastAPI's default error input echo leaking an invalid secret token.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413, "Registration body too large")
    try:
        return model.model_validate_json(body)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid registration request") from None


def _hash(body: Mutation, action: str) -> str:
    values = {
        "event": body.event_id,
        "version": body.expected_version,
        "action": action,
    }
    if isinstance(body, Registration):
        values["token"] = body.push_token.get_secret_value()
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _public(row) -> dict:
    return {
        "activity_id": row["activity_id"],
        "event_id": row["event_id"],
        "version": row["version"],
        "is_active": row["is_active"],
    }


async def _owned(db: AsyncSession, activity_id: str, user_id: int):
    result = await db.execute(
        select(_TABLE).where(
            _TABLE.c.activity_id == activity_id, _TABLE.c.user_id == user_id
        )
    )
    return result.mappings().one_or_none()


@router.get("/{activity_id}")
async def get_registration(
    activity_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_rw),
):
    row = await _owned(db, _activity_id(activity_id), user.id)
    if row is None:
        raise HTTPException(404, "Registration not found")
    return _public(row)


async def _mutate(
    request: Request, activity_id: str, user: User, db: AsyncSession, *, revoke: bool
):
    activity_id = _activity_id(activity_id)
    body = await _body(request, Mutation if revoke else Registration)
    action = "revoke" if revoke else "register"
    request_hash = _hash(body, action)
    mutation_id = str(body.mutation_id)
    row = await _owned(db, activity_id, user.id)
    if row is not None:
        if row["event_id"] != body.event_id:
            raise HTTPException(409, "Registration conflict")
        # Idempotency only for the exact latest successful operation. An older
        # retry after a later mutation conflicts; it never restores an old token.
        if row["mutation_id"] == mutation_id:
            if row["request_hash"] != request_hash:
                raise HTTPException(409, "Registration conflict")
            return _public(row)
        if not row["is_active"] or row["version"] != body.expected_version:
            raise HTTPException(409, "Registration conflict")
    elif body.expected_version != 0:
        raise HTTPException(404, "Registration not found")

    token = None if revoke else body.push_token.get_secret_value()
    token_hash = None if token is None else hashlib.sha256(token.encode()).hexdigest()
    values = {
        "version": body.expected_version + 1,
        "is_active": not revoke,
        "push_token": token,
        "token_hash": token_hash,
        "mutation_id": mutation_id,
        "request_hash": request_hash,
        "updated_at": func.now(),
    }
    try:
        if row is None:
            exists = await db.execute(select(Event.id).where(Event.id == body.event_id))
            if exists.scalar_one_or_none() is None:
                raise HTTPException(404, "Event not found")
            statement = (
                insert(_TABLE)
                .values(
                    activity_id=activity_id,
                    user_id=user.id,
                    event_id=body.event_id,
                    **values
                )
                .on_conflict_do_nothing(index_elements=[_TABLE.c.activity_id])
                .returning(*_TABLE.c)
            )
        else:
            # Atomic authoritative CAS, including immutable owner/event and active
            # tombstone fence. The earlier lookup is never the mutation authority.
            statement = (
                update(_TABLE)
                .where(
                    _TABLE.c.activity_id == activity_id,
                    _TABLE.c.user_id == user.id,
                    _TABLE.c.event_id == body.event_id,
                    _TABLE.c.version == body.expected_version,
                    _TABLE.c.is_active.is_(True),
                )
                .values(**values)
                .returning(*_TABLE.c)
            )
        mutation_result = await db.execute(statement)
        changed = mutation_result.mappings().one_or_none()
        if changed is None:
            await db.rollback()
            raise HTTPException(409, "Registration conflict")
        public = _public(changed)
        await db.commit()
        return public
    except IntegrityError:
        await db.rollback()
        # SQL errors contain bound credentials: never log, chain or expose them.
        raise HTTPException(409, "Registration conflict") from None
    except DBAPIError:
        await db.rollback()
        raise HTTPException(503, "Registration temporarily unavailable") from None


@router.put("/{activity_id}")
async def register(
    activity_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_rw),
):
    return await _mutate(request, activity_id, user, db, revoke=False)


@router.delete("/{activity_id}")
async def revoke(
    activity_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_rw),
):
    return await _mutate(request, activity_id, user, db, revoke=True)
