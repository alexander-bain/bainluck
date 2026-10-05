"""Unmounted eight-hour credential fence and bounded cleanup for #10564.

Operational authorization clocks never replace producer observation clocks.
Every mutation locks registration before delivery; tombstones are never deleted.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable
from sqlalchemy import or_, select, update
from app.models.activitykit import ActivityKitRegistration
from app.models.activitykit_delivery import ActivityKitDelivery
from app.services.activitykit_state_codec import decode_state, encode_state
from app.utils.activitykit_delivery_state import DeliveryState, RetryPolicy

AUTHORIZATION_LIFETIME = timedelta(hours=8)
REG = ActivityKitRegistration.__table__
DEL = ActivityKitDelivery.__table__


def utc_now():
    return datetime.now(timezone.utc)


def operational_time(value):
    if not isinstance(value, datetime):
        raise ValueError("Operational clock required")
    # SQLite gate returns naive stored timestamps; PostgreSQL is timezone-aware.
    return (
        value.replace(tzinfo=timezone.utc)
        if value.utcoffset() is None
        else value.astimezone(timezone.utc)
    )


def horizon_open(reg, now):
    if (
        reg is None
        or not reg["is_active"]
        or not reg["push_token"]
        or not reg["token_hash"]
    ):
        return False
    created, expires = reg["created_at"], reg["expires_at"]
    return (
        isinstance(created, datetime)
        and isinstance(expires, datetime)
        and operational_time(created)
        <= operational_time(now)
        < operational_time(expires)
        and operational_time(expires)
        <= operational_time(created) + AUTHORIZATION_LIFETIME
    )


async def erase_authorization(db, reg, *, now, mutation_id=None, request_hash=None):
    """Caller owns registration lock. Clear secrets even if delivery JSON is corrupt."""
    row = (
        (
            await db.execute(
                select(DEL)
                .where(DEL.c.activity_id == reg["activity_id"])
                .with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        try:
            state = decode_state(row["state"])
            if (state.activity_id, state.event_id) != (
                reg["activity_id"],
                reg["event_id"],
            ):
                raise ValueError("Identity mismatch")
        except ValueError:
            # Corrupt state cannot retain usable credentials. A closed, no-content
            # state preserves immutable identity and permits no future dispatch.
            state = DeliveryState(reg["activity_id"], reg["event_id"], RetryPolicy(()))
        state = replace(state, stopped=True, pending=None, attempt=None)
        await db.execute(
            update(DEL)
            .where(DEL.c.activity_id == reg["activity_id"])
            .values(
                state=encode_state(state),
                lease_id=None,
                lease_expires_at=None,
            )
        )
    changed = bool(
        reg["is_active"]
        or reg["push_token"] is not None
        or reg["token_hash"] is not None
    )
    values = dict(is_active=False, push_token=None, token_hash=None)
    if changed:
        values.update(
            version=min(reg["version"] + 1, (1 << 63) - 1),
            updated_at=operational_time(now),
        )
    if mutation_id is not None:
        values.update(mutation_id=mutation_id, request_hash=request_hash)
    return (
        (
            await db.execute(
                update(REG)
                .where(REG.c.activity_id == reg["activity_id"])
                .values(**values)
                .returning(*REG.c)
            )
        )
        .mappings()
        .one()
    )


async def cleanup_expired(sessions, *, batch_size=100, clock: Callable = utc_now):
    """Bounded source caller only; no schedule, transport, or production mounting."""
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("Cleanup batch must be in [1, 1000]")
    async with sessions() as db, db.begin():
        cutoff = operational_time(clock())
        rows = (
            (
                await db.execute(
                    select(REG)
                    .where(
                        or_(
                            REG.c.is_active.is_(True),
                            REG.c.push_token.is_not(None),
                            REG.c.token_hash.is_not(None),
                        ),
                        or_(
                            REG.c.is_active.is_(False),
                            REG.c.created_at.is_(None),
                            REG.c.expires_at.is_(None),
                            REG.c.expires_at <= cutoff,
                            REG.c.created_at > cutoff,
                            REG.c.expires_at
                            > REG.c.created_at + AUTHORIZATION_LIFETIME,
                        ),
                    )
                    .order_by(REG.c.activity_id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .all()
        )
        cleaned = 0
        for reg in rows:
            now = operational_time(clock())  # after locks, never the pre-wait time
            if not horizon_open(reg, now):
                await erase_authorization(db, reg, now=now)
                cleaned += 1
        return cleaned
